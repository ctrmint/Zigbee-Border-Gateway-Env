/* Application-owned Wi-Fi recovery; no changes to the shared ESP-IDF SDK. */
#include <string.h>
#include <stdio.h>
#include <errno.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_attr.h"
#include "nvs.h"
#include "lwip/sockets.h"
#include "mbedtls/md.h"
#include "gateway_api.h"
#include "gateway_json.h"
#include "gateway_network.h"
#include "gateway_network_policy.h"

static const char *TAG="GW_NETWORK";
static QueueHandle_t queue;
static esp_netif_t *netif;
static wifi_config_t real_config;
static portMUX_TYPE guard=portMUX_INITIALIZER_UNLOCKED;
static char identity[13];
static RTC_NOINIT_ATTR struct {uint32_t magic,guard,cause;} recovery_rtc;
#define reboot_guard recovery_rtc.guard
#define recovery_reboot_cause recovery_rtc.cause
static struct {
    bool associated, ip_ready, api_ok, test_active, test_pending;
    uint32_t attempts, failures, connections, reason, radio_restarts, api_restarts, event_drops;
    int rssi;
    uint64_t next_attempt, last_connected, test_until, last_progress;
    char ip[16];
    int last_error;
    uint32_t previous_reason, previous_attempts;
} state;
typedef struct { int type; uint32_t value; } message_t;
enum { DISCONNECTED=1, GOT_IP, LOST_IP, TEST_OUTAGE };
static uint64_t now_ms(void){return esp_timer_get_time()/1000;}
static void notify(int type,uint32_t value){
    message_t m={type,value};if(xQueueSend(queue,&m,0)!=pdTRUE){portENTER_CRITICAL(&guard);state.event_drops++;portEXIT_CRITICAL(&guard);}
}
static void event_handler(void *arg,esp_event_base_t base,int32_t id,void *data){
    (void)arg;
#if CONFIG_LWIP_IPV6
    if(base==WIFI_EVENT && id==WIFI_EVENT_STA_CONNECTED)esp_netif_create_ip6_linklocal(netif);
#endif
    if(base==WIFI_EVENT && id==WIFI_EVENT_STA_DISCONNECTED)notify(DISCONNECTED,((wifi_event_sta_disconnected_t*)data)->reason);
    if(base==IP_EVENT && id==IP_EVENT_STA_GOT_IP)notify(GOT_IP,0);
    if(base==IP_EVENT && id==IP_EVENT_STA_LOST_IP)notify(LOST_IP,0);
}
/* Discovery proves possession of the existing token without broadcasting it. */
static void discovery(int fd){
    for(int i=0;i<4;i++){
        char buf[512];struct sockaddr_in peer;socklen_t len=sizeof(peer);
        int n=recvfrom(fd,buf,sizeof(buf)-1,MSG_DONTWAIT,(struct sockaddr*)&peer,&len);if(n<=0)return;buf[n]=0;
        /* Discovery is flat JSON only: bound parser depth on this public socket. */
        unsigned braces=0;bool flat=true;for(int j=0;j<n;j++){if(buf[j]=='{' && ++braces>1)flat=false;if(buf[j]=='['||buf[j]==']')flat=false;}if(!flat)continue;
        cJSON *o=gateway_parse_command(buf,n),*op=cJSON_GetObjectItemCaseSensitive(o,"op"),*nonce=cJSON_GetObjectItemCaseSensitive(o,"nonce"),*auth=cJSON_GetObjectItemCaseSensitive(o,"proof");
        bool valid=cJSON_IsObject(o)&&cJSON_GetArraySize(o)==3&&cJSON_IsString(auth)&&strlen(auth->valuestring)==64&&cJSON_IsString(op)&&!strcmp(op->valuestring,"discover_gateway")&&cJSON_IsString(nonce)&&strlen(nonce->valuestring)==32;
        if(valid)for(int j=0;j<32;j++)if(!strchr("0123456789abcdef",nonce->valuestring[j]))valid=false;
        if(valid){
            char payload[80],proof[65],reply[512];unsigned char digest[32];
            snprintf(payload,sizeof(payload),"discover|%s",nonce->valuestring);
            mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),(const unsigned char*)CONFIG_GW_API_TOKEN,strlen(CONFIG_GW_API_TOKEN),(unsigned char*)payload,strlen(payload),digest);
            for(int j=0;j<32;j++)snprintf(proof+j*2,3,"%02x",digest[j]);
            unsigned diff=0;for(int j=0;j<64;j++)diff|=(unsigned char)proof[j]^(unsigned char)auth->valuestring[j];
            if(diff){cJSON_Delete(o);continue;}
            snprintf(payload,sizeof(payload),"%s|%s|80",nonce->valuestring,identity);
            mbedtls_md_hmac(mbedtls_md_info_from_type(MBEDTLS_MD_SHA256),(const unsigned char*)CONFIG_GW_API_TOKEN,strlen(CONFIG_GW_API_TOKEN),(unsigned char*)payload,strlen(payload),digest);
            for(int j=0;j<32;j++)snprintf(proof+j*2,3,"%02x",digest[j]);
            snprintf(reply,sizeof(reply),"{\"gateway_id\":\"%s\",\"port\":80,\"nonce\":\"%s\",\"proof\":\"%s\",\"uptime_ms\":%llu,\"ip_ready\":%s,\"api_running\":%s,\"api_ok\":%s,\"api_restarts\":%lu,\"zigbee_ready\":%s,\"heap\":%lu}",identity,nonce->valuestring,proof,(unsigned long long)now_ms(),state.ip_ready?"true":"false",gateway_api_running()?"true":"false",state.api_ok?"true":"false",(unsigned long)state.api_restarts,gateway_api_is_ready()?"true":"false",(unsigned long)esp_get_free_heap_size());
            sendto(fd,reply,strlen(reply),0,(struct sockaddr*)&peer,len);
        }cJSON_Delete(o);
    }
}
static bool http_probe(void){
    int fd=socket(AF_INET,SOCK_STREAM,0);if(fd<0)return false;
    struct timeval tv={.tv_sec=1};setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&tv,sizeof(tv));setsockopt(fd,SOL_SOCKET,SO_SNDTIMEO,&tv,sizeof(tv));
    esp_netif_ip_info_t local={0};esp_netif_get_ip_info(netif,&local);
    struct sockaddr_in addr={.sin_family=AF_INET,.sin_port=htons(80),.sin_addr.s_addr=local.ip.addr};
    char req[256],response[64];bool ok=false;
    if(connect(fd,(struct sockaddr*)&addr,sizeof(addr))==0){
        int size=snprintf(req,sizeof(req),"GET /api/v1/health HTTP/1.0\r\nHost: localhost\r\nAuthorization: Bearer %s\r\nConnection: close\r\n\r\n",CONFIG_GW_API_TOKEN);
        if(send(fd,req,size,0)==size){int n=recv(fd,response,sizeof(response)-1,0);if(n>0){response[n]=0;ok=strstr(response," 200 ")!=NULL;}}
    }close(fd);return ok;
}
static void worker(void *arg){
    (void)arg;
    int udp=socket(AF_INET,SOCK_DGRAM,0);struct sockaddr_in bind_addr={.sin_family=AF_INET,.sin_port=htons(39128),.sin_addr.s_addr=INADDR_ANY};
    if(udp>=0 && bind(udp,(struct sockaddr*)&bind_addr,sizeof(bind_addr))!=0){close(udp);udp=-1;}
    wifi_config_t target_config=real_config;bool config_pending=false;
    bool connecting=false,was_ready=false;uint64_t connect_deadline=0,dhcp_deadline=0,probe_at=0,last_radio=0,stable_since=0,last_store=0;
    unsigned driver_errors=0,probe_errors=0,dhcp_retries=0;uint64_t next_udp=0,api_start_at=0;
    nvs_handle_t nv;if(nvs_open("gw_net",NVS_READONLY,&nv)==ESP_OK){nvs_get_u32(nv,"reason",&state.previous_reason);nvs_get_u32(nv,"attempts",&state.previous_attempts);nvs_close(nv);}
    for(;;){
        uint64_t now=now_ms();message_t m;portENTER_CRITICAL(&guard);state.last_progress=now;portEXIT_CRITICAL(&guard);
        while(xQueueReceive(queue,&m,0)==pdTRUE){
            if(m.type==DISCONNECTED){
                portENTER_CRITICAL(&guard);state.reason=m.value;portEXIT_CRITICAL(&guard);
                portENTER_CRITICAL(&guard);
                bool changed=gw_net_disconnected(&connecting,&was_ready,&state.failures,&state.next_attempt,now,esp_random());
                portEXIT_CRITICAL(&guard);if(changed)stable_since=0;
            }
            if(m.type==LOST_IP && !dhcp_deadline)dhcp_deadline=now+30000;
            /* GOT_IP is a hint only; actual link/IP state below rejects stale callbacks. */
            if(m.type==TEST_OUTAGE){
                wifi_config_t missing=real_config;memset(missing.sta.ssid,0,sizeof(missing.sta.ssid));snprintf((char*)missing.sta.ssid,sizeof(missing.sta.ssid),"gw28-unavailable-%08lx",(unsigned long)esp_random());
                esp_wifi_disconnect();target_config=missing;config_pending=true;
                connecting=false;was_ready=false;stable_since=0;
                portENTER_CRITICAL(&guard);state.test_pending=false;state.test_active=true;state.test_until=now+(uint64_t)m.value*1000;state.next_attempt=now;portEXIT_CRITICAL(&guard);
            }
        }
        if(state.test_active && now>=state.test_until){
            esp_wifi_disconnect();target_config=real_config;config_pending=true;connecting=false;was_ready=false;
            portENTER_CRITICAL(&guard);state.test_active=false;state.next_attempt=now;portEXIT_CRITICAL(&guard);
        }
        if(config_pending){esp_err_t e=esp_wifi_set_config(WIFI_IF_STA,&target_config);if(e==ESP_OK)config_pending=false;else esp_wifi_disconnect();}
        wifi_ap_record_t ap;esp_netif_ip_info_t ip={0};
        bool associated=esp_wifi_sta_get_ap_info(&ap)==ESP_OK;esp_netif_get_ip_info(netif,&ip);
        bool ready=associated && esp_netif_is_netif_up(netif) && ip.ip.addr!=0;
        portENTER_CRITICAL(&guard);state.associated=associated;state.ip_ready=ready;if(!ready)state.api_ok=false;state.rssi=associated?ap.rssi:0;
        if(ready)snprintf(state.ip,sizeof(state.ip),IPSTR,IP2STR(&ip.ip));else state.ip[0]=0;
        portEXIT_CRITICAL(&guard);
        if(ready){
            if(!gateway_api_running() && now>=api_start_at){
                esp_err_t started=gateway_api_start();api_start_at=now+5000;
                portENTER_CRITICAL(&guard);state.last_error=started;portEXIT_CRITICAL(&guard);
            }
            connecting=false;dhcp_deadline=0;dhcp_retries=0;driver_errors=0;
            if(!was_ready){portENTER_CRITICAL(&guard);state.connections=gw_net_increment(state.connections);state.last_connected=now;portEXIT_CRITICAL(&guard);stable_since=now;probe_at=now;}
            if(stable_since && now-stable_since>=10000){portENTER_CRITICAL(&guard);state.failures=0;portEXIT_CRITICAL(&guard);}
            if(stable_since && now-stable_since>=300000 && state.api_ok)reboot_guard=0;
            if(now>=probe_at){bool ok=http_probe();portENTER_CRITICAL(&guard);state.api_ok=ok;portEXIT_CRITICAL(&guard);probe_at=now+30000;
                if(ok)probe_errors=0;else if(++probe_errors>=3){gateway_api_restart();probe_errors=0;portENTER_CRITICAL(&guard);state.api_restarts++;portEXIT_CRITICAL(&guard);}}
        }else if(associated){
            connecting=false;if(!dhcp_deadline)dhcp_deadline=now+30000;
            if(now>=dhcp_deadline){
                if(++dhcp_retries>=3){esp_wifi_disconnect();dhcp_retries=0;}else{esp_netif_dhcpc_stop(netif);esp_netif_dhcpc_start(netif);}
                dhcp_deadline=now+30000;
            }
        }else{
            dhcp_deadline=0;
            if(was_ready){stable_since=0;portENTER_CRITICAL(&guard);state.next_attempt=now;portEXIT_CRITICAL(&guard);}
            if(connecting && now>=connect_deadline){esp_wifi_disconnect();connecting=false;portENTER_CRITICAL(&guard);state.failures=gw_net_increment(state.failures);state.next_attempt=now+gw_net_backoff_ms(state.failures,esp_random());portEXIT_CRITICAL(&guard);}
            if(!connecting && !config_pending && now>=state.next_attempt){
                esp_err_t err=esp_wifi_connect();portENTER_CRITICAL(&guard);state.attempts=gw_net_increment(state.attempts);state.last_error=err;portEXIT_CRITICAL(&guard);
                if(err==ESP_OK){connecting=true;connect_deadline=now+25000;driver_errors=0;}
                else {driver_errors++;portENTER_CRITICAL(&guard);state.failures=gw_net_increment(state.failures);state.next_attempt=now+gw_net_backoff_ms(state.failures,esp_random());portEXIT_CRITICAL(&guard);}
                ESP_LOGI(TAG,"Recovery attempt %lu result %d",(unsigned long)state.attempts,(int)err);
            }
            if(gw_net_escalate(driver_errors,now,last_radio)){
                last_radio=now;esp_wifi_stop();esp_err_t e=esp_wifi_start();
                portENTER_CRITICAL(&guard);state.radio_restarts++;portEXIT_CRITICAL(&guard);
                if(e!=ESP_OK && state.radio_restarts>=3 && gw_net_can_reboot(reboot_guard!=0,now)){reboot_guard=1;recovery_reboot_cause=1;esp_restart();}
                driver_errors=0;
            }
        }
        was_ready=ready;
        if(state.reason && (!last_store||now-last_store>=3600000)){
            if(nvs_open("gw_net",NVS_READWRITE,&nv)==ESP_OK){nvs_set_u32(nv,"reason",state.reason);nvs_set_u32(nv,"attempts",state.attempts);nvs_commit(nv);nvs_close(nv);}last_store=now;
        }
        if(udp<0 && now>=next_udp){udp=socket(AF_INET,SOCK_DGRAM,0);if(udp>=0 && bind(udp,(struct sockaddr*)&bind_addr,sizeof(bind_addr))!=0){close(udp);udp=-1;}next_udp=now+10000;}
        if(udp>=0)discovery(udp);
        vTaskDelay(pdMS_TO_TICKS(200));
    }
}
static void progress_watchdog(void *arg){
    (void)arg;
    for(;;){vTaskDelay(pdMS_TO_TICKS(1000));uint64_t now=now_ms();
        portENTER_CRITICAL(&guard);uint64_t progress=state.last_progress;portEXIT_CRITICAL(&guard);
        if(now>progress+20000 && gw_net_can_reboot(reboot_guard!=0,now)){
            ESP_LOGE(TAG,"Network worker stalled; controlled recovery reboot");reboot_guard=1;recovery_reboot_cause=2;esp_restart();
        }
    }
}
esp_err_t gateway_network_start(void){
    if(esp_reset_reason()!=ESP_RST_SW || recovery_rtc.magic!=0x47574e32 || recovery_rtc.guard>1 || recovery_rtc.cause>2){
        recovery_rtc.magic=0x47574e32;recovery_rtc.guard=0;recovery_rtc.cause=0;
    }
    uint8_t mac[6];ESP_ERROR_CHECK(esp_read_mac(mac,ESP_MAC_WIFI_STA));snprintf(identity,sizeof(identity),"%02x%02x%02x%02x%02x%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    netif=esp_netif_create_default_wifi_sta();if(!netif)return ESP_ERR_NO_MEM;
    queue=xQueueCreate(16,sizeof(message_t));if(!queue)return ESP_ERR_NO_MEM;
    wifi_init_config_t init=WIFI_INIT_CONFIG_DEFAULT();ESP_ERROR_CHECK(esp_wifi_init(&init));
    ESP_ERROR_CHECK(esp_event_handler_register(WIFI_EVENT,ESP_EVENT_ANY_ID,event_handler,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_GOT_IP,event_handler,NULL));
    ESP_ERROR_CHECK(esp_event_handler_register(IP_EVENT,IP_EVENT_STA_LOST_IP,event_handler,NULL));
    size_t ssid_len=strlen(CONFIG_EXAMPLE_WIFI_SSID),password_len=strlen(CONFIG_EXAMPLE_WIFI_PASSWORD);
    if(ssid_len>sizeof(real_config.sta.ssid)||password_len>sizeof(real_config.sta.password))return ESP_ERR_INVALID_ARG;
    memcpy(real_config.sta.ssid,CONFIG_EXAMPLE_WIFI_SSID,ssid_len);memcpy(real_config.sta.password,CONFIG_EXAMPLE_WIFI_PASSWORD,password_len);
    real_config.sta.threshold.authmode=password_len?WIFI_AUTH_WPA2_PSK:WIFI_AUTH_OPEN;
    ESP_ERROR_CHECK(esp_wifi_set_storage(WIFI_STORAGE_RAM));ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA,&real_config));ESP_ERROR_CHECK(esp_wifi_start());ESP_ERROR_CHECK(esp_wifi_set_ps(WIFI_PS_NONE));
    if(xTaskCreate(worker,"gw_network",6144,NULL,4,NULL)!=pdPASS)return ESP_ERR_NO_MEM;
    return xTaskCreate(progress_watchdog,"gw_net_watch",2048,NULL,6,NULL)==pdPASS?ESP_OK:ESP_ERR_NO_MEM;
}
void gateway_network_health(cJSON *health){
    portENTER_CRITICAL(&guard);__typeof__(state) s=state;portEXIT_CRITICAL(&guard);
    cJSON_AddStringToObject(health,"gateway_id",identity);cJSON *o=cJSON_AddObjectToObject(health,"network");
    cJSON_AddBoolToObject(o,"associated",s.associated);cJSON_AddBoolToObject(o,"ip_ready",s.ip_ready);cJSON_AddBoolToObject(o,"api_ok",s.api_ok);cJSON_AddStringToObject(o,"ipv4",s.ip);
    cJSON_AddNumberToObject(o,"attempts",s.attempts);cJSON_AddNumberToObject(o,"consecutive_failures",s.failures);cJSON_AddNumberToObject(o,"last_disconnect_reason",s.reason);cJSON_AddNumberToObject(o,"connections",s.connections);
    cJSON_AddNumberToObject(o,"next_attempt_ms",s.next_attempt);cJSON_AddNumberToObject(o,"last_connected_ms",s.last_connected);if(s.associated)cJSON_AddNumberToObject(o,"wifi_rssi",s.rssi);else cJSON_AddNullToObject(o,"wifi_rssi");
    cJSON_AddNumberToObject(o,"radio_restarts",s.radio_restarts);cJSON_AddNumberToObject(o,"api_restarts",s.api_restarts);cJSON_AddNumberToObject(o,"event_drops",s.event_drops);cJSON_AddNumberToObject(o,"last_driver_error",s.last_error);
    cJSON_AddNumberToObject(o,"previous_disconnect_reason",s.previous_reason);cJSON_AddNumberToObject(o,"previous_attempts",s.previous_attempts);cJSON_AddNumberToObject(o,"reset_reason",esp_reset_reason());cJSON_AddNumberToObject(o,"recovery_reboot_cause",recovery_reboot_cause);cJSON_AddNumberToObject(o,"last_progress_ms",s.last_progress);
    cJSON_AddBoolToObject(o,"test_active",s.test_active);cJSON_AddNumberToObject(o,"test_until_ms",s.test_until);
#ifdef CONFIG_GW_NETWORK_TEST
    cJSON_AddBoolToObject(o,"test_enabled",true);
#else
    cJSON_AddBoolToObject(o,"test_enabled",false);
#endif
}
esp_err_t gateway_network_test(const cJSON *o){
#ifdef CONFIG_GW_NETWORK_TEST
    cJSON *seconds=cJSON_GetObjectItemCaseSensitive(o,"seconds");
    if(!cJSON_IsObject(o)||cJSON_GetArraySize(o)!=1||!cJSON_IsNumber(seconds)||seconds->valuedouble!=seconds->valueint||seconds->valueint<1||seconds->valueint>300)return ESP_ERR_INVALID_ARG;
    portENTER_CRITICAL(&guard);bool busy=state.test_active||state.test_pending;if(!busy)state.test_pending=true;portEXIT_CRITICAL(&guard);
    if(busy)return ESP_ERR_INVALID_STATE;
    message_t m={TEST_OUTAGE,(uint32_t)seconds->valueint};if(xQueueSend(queue,&m,0)==pdTRUE)return ESP_OK;
    portENTER_CRITICAL(&guard);state.test_pending=false;portEXIT_CRITICAL(&guard);return ESP_ERR_NO_MEM;
#else
    (void)o;return ESP_ERR_NOT_SUPPORTED;
#endif
}
