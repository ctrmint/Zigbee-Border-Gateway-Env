/* SPDX-License-Identifier: MIT */
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include <inttypes.h>
#include <math.h>
#include "gateway_api.h"
#include "gateway_cursor.h"
#include "gateway_json.h"
#include "gateway_reporting.h"
#include "gateway_clock.h"
#include "gateway_network.h"
#include "esp_http_server.h"
#include "esp_random.h"
#include "esp_timer.h"
#include "nvs.h"
#include "cJSON.h"
#include "freertos/semphr.h"

#define MAX_DEVICES 50
#define EVENT_SLOTS 64
#define EVENT_BYTES 768
/* No network I/O in stack callbacks. Fixed event ring bounds heap usage. */
typedef struct { uint64_t ieee; uint16_t nwk; bool used, active; } device_t;
static device_t devices[MAX_DEVICES];
static char events[EVENT_SLOTS][EVENT_BYTES];
static uint32_t seq;
static char boot_id[17];
static SemaphoreHandle_t mutex;
static bool ready;
static int64_t join_until;
static uint32_t dropped;
static uint16_t pan_id;
static uint8_t channel;

void gateway_emit(cJSON *o)
{
    if (!o) return;
    xSemaphoreTake(mutex, portMAX_DELAY);
    if(!cJSON_GetObjectItemCaseSensitive(o,"ieee")){
        cJSON *addr=cJSON_GetObjectItemCaseSensitive(o,"nwk");
        if(cJSON_IsNumber(addr))for(int i=0;i<MAX_DEVICES;i++)if(devices[i].used&&devices[i].active&&devices[i].nwk==addr->valueint){
            char value[17];snprintf(value,sizeof(value),"%016" PRIx64,devices[i].ieee);cJSON_AddStringToObject(o,"ieee",value);break;
        }
    }
    /* Start a new cursor epoch before uint32_t wraps; pollers reset by boot_id. */
    if(seq==UINT32_MAX){
        snprintf(boot_id,sizeof(boot_id),"%08" PRIx32 "%08" PRIx32,esp_random(),esp_random());
        seq=0;
        memset(events,0,sizeof(events));
    }
    cJSON_AddNumberToObject(o, "seq", seq + 1);
    cJSON_AddNumberToObject(o, "uptime_ms", esp_timer_get_time()/1000);
    char *s = cJSON_PrintUnformatted(o);
    if (s && strlen(s) < EVENT_BYTES) {
        seq++;
        strcpy(events[seq % EVENT_SLOTS], s);
    } else dropped++;
    free(s);
    xSemaphoreGive(mutex);
    cJSON_Delete(o);
}
static cJSON *event(const char *type, uint16_t nwk)
{
    cJSON *o=cJSON_CreateObject();
    cJSON_AddStringToObject(o,"type",type);
    cJSON_AddNumberToObject(o,"nwk",nwk);
    xSemaphoreTake(mutex,portMAX_DELAY);
    for(int i=0;i<MAX_DEVICES;i++) if(devices[i].used && devices[i].active && devices[i].nwk==nwk){
        char s[17]; snprintf(s,sizeof(s),"%016" PRIx64,devices[i].ieee);
        cJSON_AddStringToObject(o,"ieee",s); break;
    }
    xSemaphoreGive(mutex); return o;
}
static void save_registry(void)
{
    nvs_handle_t n;
    if(nvs_open("gw_registry",NVS_READWRITE,&n)==ESP_OK){
        nvs_set_blob(n,"devices",devices,sizeof(devices)); nvs_commit(n); nvs_close(n);
    }
}
static void simple_cb(const ezb_zdo_simple_desc_req_result_t *res,void *ctx)
{
    ezb_zdo_simple_desc_req_t *req=ctx;
    cJSON *o=event("endpoint",req->dst_nwk_addr);
    cJSON_AddNumberToObject(o,"endpoint",req->field.endpoint);
    bool ok=res->error==EZB_ERR_NONE && res->rsp && res->rsp->status==0;
    cJSON_AddBoolToObject(o,"ok",ok);
    if(ok){
        ezb_af_simple_desc_t *d=&res->rsp->desc;
        cJSON_AddNumberToObject(o,"profile_id",d->app_profile_id);
        cJSON_AddNumberToObject(o,"device_id",d->app_device_id);
        cJSON *in=cJSON_AddArrayToObject(o,"input_clusters"),*out=cJSON_AddArrayToObject(o,"output_clusters");
        for(int i=0;i<d->app_input_cluster_count;i++) cJSON_AddItemToArray(in,cJSON_CreateNumber(d->app_cluster_list[i]));
        for(int i=0;i<d->app_output_cluster_count;i++) cJSON_AddItemToArray(out,cJSON_CreateNumber(d->app_cluster_list[d->app_input_cluster_count+i]));
    }
    gateway_emit(o);
    if(ok){
        ezb_af_simple_desc_t *d=&res->rsp->desc;bool basic=false;
        for(int i=0;i<d->app_input_cluster_count;i++)if(d->app_cluster_list[i]==0)basic=true;
        if(basic){
            uint16_t ids[]={4,5,0x4000};
            ezb_zcl_read_attr_cmd_t cmd={.cmd_ctrl={.dst_addr={.addr_mode=EZB_ADDR_MODE_SHORT,.u.short_addr=req->dst_nwk_addr},.dst_ep=req->field.endpoint,.src_ep=10,.cluster_id=0},.payload={.attr_number=3,.attr_field=ids}};
            ezb_zcl_read_attr_cmd_req(&cmd);
        }
    }
    free(req);
}
static void active_cb(const ezb_zdo_active_ep_req_result_t *res,void *ctx)
{
    ezb_zdo_active_ep_req_t *req=ctx;
    bool ok=res->error==EZB_ERR_NONE && res->rsp && res->rsp->status==0;
    cJSON *o=event("discovery",req->dst_nwk_addr); cJSON_AddBoolToObject(o,"ok",ok); gateway_emit(o);
    if(ok) for(int i=0;i<res->rsp->active_ep_count;i++){
        ezb_zdo_simple_desc_req_t *s=calloc(1,sizeof(*s)); if(!s) break;
        s->dst_nwk_addr=req->dst_nwk_addr; s->field.nwk_addr_of_interest=req->dst_nwk_addr;
        s->field.endpoint=res->rsp->active_ep_list[i]; s->cb=simple_cb; s->user_ctx=s;
        if(ezb_zdo_simple_desc_req(s)!=EZB_ERR_NONE) free(s);
    }
    free(req);
}
static ezb_err_t discover(uint16_t nwk)
{
    ezb_zdo_active_ep_req_t *r=calloc(1,sizeof(*r)); if(!r) return EZB_ERR_NO_MEM;
    r->dst_nwk_addr=nwk; r->field.nwk_addr_of_interest=nwk; r->cb=active_cb; r->user_ctx=r;
    ezb_err_t e=ezb_zdo_active_ep_req(r); if(e!=EZB_ERR_NONE) free(r); return e;
}
void gateway_announce(const ezb_zdo_signal_device_annce_params_t *p)
{
    gateway_plug_forget(p->short_addr);
    xSemaphoreTake(mutex,portMAX_DELAY);
    int slot=-1;
    for(int i=0;i<MAX_DEVICES;i++) if(devices[i].used && devices[i].ieee==p->device_addr.u64){slot=i;break;}
    if(slot<0) for(int i=0;i<MAX_DEVICES;i++) if(!devices[i].used){slot=i;break;}
    if(slot>=0){
        /* Short addresses can be reallocated; never keep two live owners. */
        for(int i=0;i<MAX_DEVICES;i++) if(i!=slot && devices[i].nwk==p->short_addr) devices[i].active=false;
        devices[slot]=(device_t){.ieee=p->device_addr.u64,.nwk=p->short_addr,.used=true,.active=true};
        save_registry();
    }
    xSemaphoreGive(mutex);
    cJSON *o=event(slot>=0?"announce":"registry_full",p->short_addr);
    cJSON_AddNumberToObject(o,"capability",p->capability); gateway_emit(o);
    if(slot>=0) discover(p->short_addr);
}
void gateway_leave(uint16_t nwk)
{
    gateway_plug_forget(nwk);
    gateway_emit(event("leave",nwk));
    xSemaphoreTake(mutex,portMAX_DELAY);
    for(int i=0;i<MAX_DEVICES;i++) if(devices[i].used && devices[i].nwk==nwk) devices[i].active=false;
    save_registry(); xSemaphoreGive(mutex);
}
static void attribute(const ezb_zcl_cmd_hdr_t *h,uint16_t id,uint8_t type,void *value,const char *origin)
{
    if(!h || !value || h->src_addr.addr_mode!=EZB_ADDR_MODE_SHORT) return;
    if(h->cluster_id==0)gateway_plug_observe(h->src_addr.u.short_addr,h->src_ep,id,type,value);
    cJSON *o=event("attribute",h->src_addr.u.short_addr);
    cJSON_AddNumberToObject(o,"endpoint",h->src_ep); cJSON_AddNumberToObject(o,"cluster",h->cluster_id);
    cJSON_AddNumberToObject(o,"attribute",id); cJSON_AddNumberToObject(o,"data_type",type);
    cJSON_AddNumberToObject(o,"rssi",h->rssi);
    cJSON_AddStringToObject(o,"origin",origin);
    /* Preserve raw standard scalar values; normalization is on the SBC. */
    double v=0; bool numeric=true;
    switch(type){
    case 0x10: case 0x18: case 0x20: case 0x30: v=*(uint8_t*)value; break;
    case 0x19: case 0x21: case 0x31: {uint16_t x;memcpy(&x,value,2);v=x;} break;
    case 0x22: {uint8_t *b=value;v=(uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16);break;}
    case 0x25: {uint64_t x=0;memcpy(&x,value,6);v=(double)x;break;}
    case 0x23: {uint32_t x;memcpy(&x,value,4);v=x;} break;
    case 0x28: v=*(int8_t*)value; break;
    case 0x29: {int16_t x;memcpy(&x,value,2);v=x;} break;
    case 0x2b: {int32_t x;memcpy(&x,value,4);v=x;} break;
    case 0x42: {
        unsigned n=*(uint8_t*)value;
        if(n!=255){
            if(h->cluster_id==0xfc11&&id==0x7003){char hex[59];if(n<=29){for(unsigned k=0;k<n;k++)snprintf(hex+2*k,3,"%02x",((uint8_t*)value)[k+1]);hex[2*n]=0;cJSON_AddStringToObject(o,"raw_hex",hex);}}
            else {char s[256];memcpy(s,(uint8_t*)value+1,n);s[n]=0;cJSON_AddStringToObject(o,"raw",s);}
        }
        numeric=false;break;
    }
    default: numeric=false; cJSON_AddBoolToObject(o,"unsupported_type",true);break;
    }
    if(numeric) cJSON_AddNumberToObject(o,"raw",v);
    gateway_emit(o);
}
void gateway_zcl_action(ezb_zcl_core_action_callback_id_t id,void *msg)
{
    if(!msg) return;
    gateway_reporting_action(id,msg);
    if(id==EZB_ZCL_CORE_REPORT_ATTR_CB_ID){
        ezb_zcl_cmd_report_attr_message_t *m=msg;
        for(ezb_zcl_report_attr_variable_t *v=m->in.variables;v;v=v->next) attribute(m->in.header,v->attr_id,v->attr_type,v->attr_value,"report");
    }else if(id==EZB_ZCL_CORE_READ_ATTR_RSP_CB_ID){
        ezb_zcl_cmd_read_attr_rsp_message_t *m=msg;
        for(ezb_zcl_read_attr_rsp_variable_t *v=m->in.variables;v;v=v->next)
            if(v->status==0) attribute(m->in.header,v->attr_id,v->attr_type,v->attr_value,"read_response");
    }else if(id==EZB_ZCL_CORE_DEFAULT_RSP_CB_ID){
        ezb_zcl_cmd_default_rsp_message_t *m=msg;
        if(m->in.header){cJSON *o=event("zcl_response",m->in.header->src_addr.u.short_addr);
            cJSON_AddNumberToObject(o,"status",m->in.status_code);cJSON_AddNumberToObject(o,"tsn",m->in.header->tsn);gateway_emit(o);}
    }
}
static esp_err_t reply(httpd_req_t *req,cJSON *o)
{
    char *s=cJSON_PrintUnformatted(o); cJSON_Delete(o);
    if(!s) return httpd_resp_send_err(req,HTTPD_500_INTERNAL_SERVER_ERROR,"allocation failed");
    httpd_resp_set_type(req,"application/json"); httpd_resp_set_hdr(req,"Cache-Control","no-store");
    esp_err_t e=httpd_resp_sendstr(req,s);free(s);return e;
}
static esp_err_t unavailable(httpd_req_t *req,const char *message)
{
    httpd_resp_set_status(req,"503 Service Unavailable");
    cJSON *o=cJSON_CreateObject();cJSON_AddStringToObject(o,"error",message);return reply(req,o);
}
static bool authorized(httpd_req_t *req)
{
    char actual[160],expected[160];
    snprintf(expected,sizeof(expected),"Bearer %s",CONFIG_GW_API_TOKEN);
    if(httpd_req_get_hdr_value_str(req,"Authorization",actual,sizeof(actual))!=ESP_OK) return false;
    size_t a=strlen(actual),b=strlen(expected);unsigned diff=a^b;
    for(size_t i=0;i<b;i++) diff|=(unsigned char)expected[i]^(i<a?(unsigned char)actual[i]:0);
    return diff==0;
}
static esp_err_t handle_get(httpd_req_t *req)
{
    if(!authorized(req)) return httpd_resp_send_err(req,HTTPD_401_UNAUTHORIZED,"token required");
    uint32_t after=0;
    const char *query=strchr(req->uri,'?');
    size_t path_len=query?(size_t)(query-req->uri):strlen(req->uri);
    bool health=path_len==strlen("/api/v1/health") && !strncmp(req->uri,"/api/v1/health",path_len);
    bool inventory=path_len==strlen("/api/v1/devices") && !strncmp(req->uri,"/api/v1/devices",path_len);
    if(!health && !inventory && query){
        /* Accept exactly one documented cursor; reject truncation and ambiguity. */
        if(strncmp(query+1,"after=",6) || !gateway_parse_cursor(query+7,&after))
            return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"invalid after cursor");
    }
    cJSON *o=cJSON_CreateObject();xSemaphoreTake(mutex,portMAX_DELAY);
    cJSON_AddStringToObject(o,"boot_id",boot_id);
    if(health){
        cJSON_AddBoolToObject(o,"ready",ready);cJSON_AddStringToObject(o,"mode","hardware");
        cJSON_AddNumberToObject(o,"uptime_ms",esp_timer_get_time()/1000);
        cJSON_AddNumberToObject(o,"join_seconds",join_until>esp_timer_get_time()?(join_until-esp_timer_get_time())/1000000:0);
        cJSON_AddNumberToObject(o,"pan_id",pan_id);cJSON_AddNumberToObject(o,"channel",channel);
        cJSON_AddBoolToObject(o,"plug_extensions",true);cJSON_AddBoolToObject(o,"reporting_commissioning",true);cJSON_AddBoolToObject(o,"sensor_extensions",true);cJSON_AddBoolToObject(o,"time_server_valid",gateway_clock_is_valid());cJSON_AddNumberToObject(o,"dropped_events",dropped);cJSON_AddNumberToObject(o,"latest_seq",seq);
        gateway_network_health(o);
    }else if(inventory){
        cJSON *a=cJSON_AddArrayToObject(o,"devices");
        for(int i=0;i<MAX_DEVICES;i++) if(devices[i].used){
            cJSON *d=cJSON_CreateObject();char s[17];snprintf(s,sizeof(s),"%016" PRIx64,devices[i].ieee);
            cJSON_AddStringToObject(d,"ieee",s);cJSON_AddNumberToObject(d,"nwk",devices[i].nwk);
            cJSON_AddBoolToObject(d,"active",devices[i].active);cJSON_AddItemToArray(a,d);
        }
    }else{
        uint32_t oldest=seq>=EVENT_SLOTS?seq-EVENT_SLOTS+1:1;
        bool gap=gateway_cursor_gap(after,oldest,seq);
        cJSON_AddBoolToObject(o,"gap",gap);
        if(gap) after=oldest-1;
        cJSON *a=cJSON_AddArrayToObject(o,"events");uint32_t end=gateway_batch_end(after,seq);
        for(uint32_t i=after;i<end;){++i;cJSON_AddItemToArray(a,cJSON_Parse(events[i%EVENT_SLOTS]));}
        cJSON_AddNumberToObject(o,"next_seq",end);cJSON_AddNumberToObject(o,"latest_seq",seq);
    }
    xSemaphoreGive(mutex);return reply(req,o);
}
static bool integer(cJSON *o,const char *key,int min,int max,int *out)
{
    cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);
    if(!cJSON_IsNumber(v) || !isfinite(v->valuedouble) || v->valuedouble!=floor(v->valuedouble) || v->valuedouble<min || v->valuedouble>max) return false;
    *out=v->valueint;return true;
}
static esp_err_t command(httpd_req_t *req)
{
    if(!authorized(req)) return httpd_resp_send_err(req,HTTPD_401_UNAUTHORIZED,"token required");
    if(req->content_len<=0 || req->content_len>512) return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"body size");
    char body[513];int n=0;
    while(n<req->content_len){int x=httpd_req_recv(req,body+n,req->content_len-n);if(x<=0) return ESP_FAIL;n+=x;}body[n]=0;
    cJSON *o=gateway_parse_command(body,(size_t)n);
    if(!o) return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"invalid command JSON");
    cJSON *op=cJSON_GetObjectItemCaseSensitive(o,"op");
    if(!cJSON_IsString(op)){cJSON_Delete(o);return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"op required");}
    xSemaphoreTake(mutex,portMAX_DELAY);bool is_ready=ready;xSemaphoreGive(mutex);
    if(!is_ready){cJSON_Delete(o);return unavailable(req,"stack not ready");}
    int seconds=0,ep=0,cluster=0,attr=0;uint16_t nwk=0xffff;
    bool join=!strcmp(op->valuestring,"permit_join");
    bool disc=!strcmp(op->valuestring,"discover"), read=!strcmp(op->valuestring,"read"), onoff=!strcmp(op->valuestring,"on_off");
    bool clock=!strcmp(op->valuestring,"sync_clock");
    bool reporting=gateway_reporting_operation(op->valuestring);uint64_t device_ieee=0;
    bool valid=join?integer(o,"seconds",0,180,&seconds):false;
    if(disc||read||onoff||reporting){
        cJSON *ieee=cJSON_GetObjectItemCaseSensitive(o,"ieee");
        if(cJSON_IsString(ieee) && strlen(ieee->valuestring)==16 && strspn(ieee->valuestring,"0123456789abcdefABCDEF")==16){
            uint64_t id=strtoull(ieee->valuestring,NULL,16);device_ieee=id;xSemaphoreTake(mutex,portMAX_DELAY);
            for(int i=0;i<MAX_DEVICES;i++) if(devices[i].used && devices[i].active && devices[i].ieee==id) nwk=devices[i].nwk;
            xSemaphoreGive(mutex);
        }
        valid=nwk<0xfff8;
        if(read||onoff) valid=valid&&integer(o,"endpoint",1,240,&ep);
        if(read) valid=valid&&integer(o,"cluster",0,65535,&cluster)&&integer(o,"attribute",0,65535,&attr);
        if(onoff){cJSON *state=cJSON_GetObjectItemCaseSensitive(o,"state");valid=valid&&cJSON_IsBool(state);}
    }
    if(clock) valid=gateway_clock_valid_command(o);
    if(reporting) valid=valid&&gateway_reporting_valid(o);
    if(!valid){cJSON_Delete(o);return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"invalid command or unknown device");}
    if(!esp_zigbee_lock_acquire(pdMS_TO_TICKS(1000))){cJSON_Delete(o);return unavailable(req,"stack busy");}
    ezb_err_t e=EZB_ERR_FAIL;
    if(clock){gateway_clock_sync(o);e=EZB_ERR_NONE;}
    else if(join){e=ezb_bdb_open_network(seconds);if(e==EZB_ERR_NONE){xSemaphoreTake(mutex,portMAX_DELAY);join_until=esp_timer_get_time()+(int64_t)seconds*1000000;xSemaphoreGive(mutex);}}
    else if(reporting) e=gateway_reporting_command(o,device_ieee,nwk);
    else if(disc) e=discover(nwk);
    else if(onoff){
        ezb_zcl_on_off_cmd_t c={.cmd_ctrl={.dst_addr={.addr_mode=EZB_ADDR_MODE_SHORT,.u.short_addr=nwk},.dst_ep=ep,.src_ep=10}};
        e=cJSON_IsTrue(cJSON_GetObjectItemCaseSensitive(o,"state"))?ezb_zcl_on_off_on_cmd_req(&c):ezb_zcl_on_off_off_cmd_req(&c);
    }else if(read){
        uint16_t a=attr;
        ezb_zcl_read_attr_cmd_t c={.cmd_ctrl={.dst_addr={.addr_mode=EZB_ADDR_MODE_SHORT,.u.short_addr=nwk},.dst_ep=ep,.src_ep=10,.cluster_id=cluster},.payload={.attr_number=1,.attr_field=&a}};
        e=ezb_zcl_read_attr_cmd_req(&c);
    }
    esp_zigbee_lock_release();cJSON_Delete(o);
    cJSON *result=cJSON_CreateObject();cJSON_AddBoolToObject(result,"accepted",e==EZB_ERR_NONE);cJSON_AddNumberToObject(result,"stack_result",e);
    httpd_resp_set_status(req,e==EZB_ERR_NONE?"202 Accepted":"503 Service Unavailable");return reply(req,result);
}
void gateway_ready(void)
{
    xSemaphoreTake(mutex,portMAX_DELAY);ready=true;pan_id=ezb_nwk_get_panid();channel=ezb_nwk_get_current_channel();xSemaphoreGive(mutex);
    gateway_emit(event("network_ready",0));
}
void gateway_permit_join_status(uint8_t seconds)
{
    xSemaphoreTake(mutex,portMAX_DELAY);
    join_until=esp_timer_get_time()+(int64_t)seconds*1000000;
    xSemaphoreGive(mutex);
}
esp_err_t gateway_api_init(void)
{
    if(strlen(CONFIG_GW_API_TOKEN)<32 || strlen(CONFIG_GW_API_TOKEN)>120) return ESP_ERR_INVALID_ARG;
    mutex=xSemaphoreCreateMutex();if(!mutex) return ESP_ERR_NO_MEM;
    snprintf(boot_id,sizeof(boot_id),"%08" PRIx32 "%08" PRIx32,esp_random(),esp_random());
    nvs_handle_t n;size_t size=sizeof(devices);
    if(nvs_open("gw_registry",NVS_READONLY,&n)==ESP_OK){nvs_get_blob(n,"devices",devices,&size);nvs_close(n);}
    return ESP_OK;
}
static httpd_handle_t server;
bool gateway_api_running(void){return server!=NULL;}
bool gateway_api_is_ready(void){return ready;}
#ifdef CONFIG_GW_NETWORK_TEST
static esp_err_t network_test(httpd_req_t *req){
    if(!authorized(req))return httpd_resp_send_err(req,HTTPD_401_UNAUTHORIZED,"token required");
    if(req->content_len<1||req->content_len>100)return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"invalid test");
    char buf[101];int got=0;
    while(got<req->content_len){int n=httpd_req_recv(req,buf+got,req->content_len-got);if(n<=0)return ESP_FAIL;got+=n;}buf[got]=0;
    cJSON *o=gateway_parse_command(buf,got);esp_err_t e=gateway_network_test(o);cJSON_Delete(o);
    if(e!=ESP_OK)return httpd_resp_send_err(req,HTTPD_400_BAD_REQUEST,"test unavailable or invalid");
    httpd_resp_set_status(req,"202 Accepted");httpd_resp_set_type(req,"application/json");return httpd_resp_sendstr(req,"{\"accepted\":true}");
}
#endif
esp_err_t gateway_api_start(void)
{
    if(server)return ESP_OK;
    httpd_config_t c=HTTPD_DEFAULT_CONFIG();c.stack_size=8192;c.lru_purge_enable=true;
    esp_err_t e=httpd_start(&server,&c);if(e!=ESP_OK){server=NULL;return e;}
    const char *paths[]={"/api/v1/health","/api/v1/devices","/api/v1/events"};
    for(int i=0;i<3;i++){httpd_uri_t u={.uri=paths[i],.method=HTTP_GET,.handler=handle_get};if((e=httpd_register_uri_handler(server,&u))!=ESP_OK)goto failed;}
    httpd_uri_t u={.uri="/api/v1/commands",.method=HTTP_POST,.handler=command};if((e=httpd_register_uri_handler(server,&u))!=ESP_OK)goto failed;
#ifdef CONFIG_GW_NETWORK_TEST
    httpd_uri_t test={.uri="/api/v1/network-test",.method=HTTP_POST,.handler=network_test};if((e=httpd_register_uri_handler(server,&test))!=ESP_OK)goto failed;
#endif
    return ESP_OK;
failed:httpd_stop(server);server=NULL;return e;
}
esp_err_t gateway_api_restart(void){
    if(server){esp_err_t e=httpd_stop(server);if(e!=ESP_OK)return e;server=NULL;}
    return gateway_api_start();
}
