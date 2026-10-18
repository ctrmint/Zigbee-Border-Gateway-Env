/* SPDX-License-Identifier: MIT */
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include <inttypes.h>
#include <math.h>
#include "gateway_reporting.h"
#include "gateway_reporting_policy.h"
#include "gateway_sensor_policy.h"
#include "gateway_plug_policy.h"
#include "ezbee/zcl/cluster/custom.h"
#include "gateway_clock.h"
#include "esp_timer.h"
#include "freertos/task.h"
#include "ezbee/zcl/cluster/poll_control.h"

#define SLOTS 16
#define TIMEOUT_US (25000000LL)
typedef struct {
    bool used,has_tsn; uintptr_t token; uint64_t ieee;
    uint16_t nwk,cluster,attribute; uint8_t ep,tsn; int64_t deadline;
    char id[37],op[24];
} pending_t;
static pending_t pending[SLOTS];
static uintptr_t next_token;
typedef struct {uint16_t nwk; int64_t until;} window_t;
static window_t windows[SLOTS];
static bool number(const cJSON *o,const char *key,int lo,int hi,int *out)
{
    cJSON *v=cJSON_GetObjectItemCaseSensitive(o,key);
    if(!cJSON_IsNumber(v)||!isfinite(v->valuedouble)||v->valuedouble!=floor(v->valuedouble)||v->valuedouble<lo||v->valuedouble>hi)return false;
    *out=v->valueint;return true;
}
static struct {uint16_t nwk;uint8_t ep;bool used,maker,model;} plug_identity[50];
void gateway_plug_forget(uint16_t nwk){for(int i=0;i<50;i++)if(plug_identity[i].used&&plug_identity[i].nwk==nwk)plug_identity[i].used=false;}
void gateway_plug_observe(uint16_t nwk,uint8_t ep,uint16_t attr,uint8_t type,const void *value)
{
    if(type!=0x42||!value||(attr!=4&&attr!=5))return;
    int slot=-1;for(int i=0;i<50;i++){if(plug_identity[i].used&&plug_identity[i].nwk==nwk&&plug_identity[i].ep==ep){slot=i;break;}if(!plug_identity[i].used)slot=i;}
    if(slot<0)return;
    if(!plug_identity[slot].used){memset(&plug_identity[slot],0,sizeof(plug_identity[slot]));plug_identity[slot].used=true;plug_identity[slot].nwk=nwk;plug_identity[slot].ep=ep;}
    const uint8_t *v=value;
    if(attr==5)plug_identity[slot].model=v[0]==8&&!memcmp(v+1,"S60ZBTPG",8);
    else plug_identity[slot].maker=(v[0]==6&&!memcmp(v+1,"SONOFF",6))||(v[0]==7&&!memcmp(v+1,"eWeLink",7));
}
static bool plug_allowed(uint16_t nwk,uint8_t ep){for(int i=0;i<50;i++)if(plug_identity[i].used&&plug_identity[i].nwk==nwk&&plug_identity[i].ep==ep)return plug_identity[i].model&&plug_identity[i].maker;return false;}
static bool plug_payload(const cJSON *o,uint8_t *b,size_t *n)
{
    cJSON *v=cJSON_GetObjectItemCaseSensitive(o,"payload");if(!cJSON_IsString(v))return false;
    size_t l=strlen(v->valuestring);if(l>58||l%2||strspn(v->valuestring,"0123456789abcdef")!=l)return false;
    *n=l/2;for(size_t i=0;i<*n;i++){char h[3]={v->valuestring[2*i],v->valuestring[2*i+1],0};b[i]=strtoul(h,NULL,16);}return true;
}
static bool plug_valid(const cJSON *o,const char *op)
{
    int c,a,v;size_t n=0;uint8_t b[29];
    if(!number(o,"cluster",0,65535,&c)||!number(o,"attribute",0,65535,&a))return false;
    if(!strcmp(op,"plug_inching"))return cJSON_GetArraySize(o)==7&&c==0xfc11&&a==0&&plug_payload(o,b,&n)&&gateway_plug_inching(b,n);
    if(!strcmp(op,"plug_relay"))return cJSON_GetArraySize(o)==7&&c==6&&a==0&&number(o,"value",0,1,&v);
    if(!strcmp(op,"plug_write")){
        if(cJSON_GetArraySize(o)!=7)return false;
        if(c==0xfc11&&a==0x7003)return plug_payload(o,b,&n)&&gateway_plug_protection(b,n);
        return number(o,"value",0,255,&v)&&gateway_plug_writable(c,a,v);
    }
    if(cJSON_GetArraySize(o)!=6)return false;
    if(!strcmp(op,"plug_bind"))return a==0&&(c==6||c==0xfc11||c==0x702);
    if(!strcmp(op,"plug_read"))return gateway_plug_type(c,a)>=0;
    int type,min,max;uint64_t change;
    return (!strcmp(op,"plug_configure")||!strcmp(op,"plug_read_reporting"))&&gateway_plug_report(c,a,&type,&min,&max,&change);
}
bool gateway_reporting_operation(const char *op)
{return !strcmp(op,"plug_read")||!strcmp(op,"plug_write")||!strcmp(op,"plug_relay")||!strcmp(op,"plug_inching")||!strcmp(op,"plug_bind")||!strcmp(op,"plug_configure")||!strcmp(op,"plug_read_reporting")||!strcmp(op,"bind")||!strcmp(op,"configure_reporting")||!strcmp(op,"read_reporting")||!strcmp(op,"reporting_window")||!strcmp(op,"write_display")||!strcmp(op,"read_display");}
bool gateway_reporting_valid(const cJSON *o)
{
    const char *op=cJSON_GetObjectItemCaseSensitive(o,"op")->valuestring;
    cJSON *rid=cJSON_GetObjectItemCaseSensitive(o,"request_id");
    int ep,cluster,attr=0,min=0,max=0,change=0,seconds;
    if(!cJSON_IsString(rid)||strlen(rid->valuestring)!=36||strspn(rid->valuestring,"0123456789abcdef-")!=36)return false;
    if(!number(o,"endpoint",1,240,&ep))return false;
    if(!strncmp(op,"plug_",5))return plug_valid(o,op);
    if(!strcmp(op,"reporting_window"))return cJSON_GetArraySize(o)==5&&number(o,"seconds",0,120,&seconds);
    if(!number(o,"cluster",0,65535,&cluster))return false;
    if(!strcmp(op,"write_display")||!strcmp(op,"read_display")){
        int type,low,high,value;
        if(cluster!=0xfc11||!number(o,"attribute",0,65535,&attr)||!gateway_display_spec(attr,&type,&low,&high))return false;
        return !strcmp(op,"read_display")?cJSON_GetArraySize(o)==6:cJSON_GetArraySize(o)==7&&number(o,"value",low,high,&value)&&gateway_display_value(attr,value);
    }
    if(!strcmp(op,"bind"))return cJSON_GetArraySize(o)==5&&(cluster==0x402||cluster==0x405||cluster==0x20||cluster==1||cluster==6);
    if(!number(o,"attribute",0,65535,&attr))return false;
    if(!strcmp(op,"read_reporting"))return cJSON_GetArraySize(o)==6&&(((cluster==0x402||cluster==0x405)&&attr==0)||(cluster==1&&(attr==32||attr==33)));
    return cJSON_GetArraySize(o)==9&&number(o,"min_interval",0,65534,&min)&&number(o,"max_interval",1,65534,&max)&&number(o,"reportable_change",1,32767,&change)&&gateway_reporting_policy(cluster,attr,min,max,change);
}
static cJSON *result(pending_t *p,const char *phase,int status)
{
    cJSON *e=cJSON_CreateObject();char ieee[17];snprintf(ieee,sizeof(ieee),"%016" PRIx64,p->ieee);
    cJSON_AddStringToObject(e,"type","commissioning");cJSON_AddStringToObject(e,"ieee",ieee);
    cJSON_AddNumberToObject(e,"nwk",p->nwk);cJSON_AddNumberToObject(e,"endpoint",p->ep);
    cJSON_AddNumberToObject(e,"cluster",p->cluster);cJSON_AddNumberToObject(e,"attribute",p->attribute);
    cJSON_AddStringToObject(e,"request_id",p->id);cJSON_AddStringToObject(e,"operation",p->op);
    cJSON_AddStringToObject(e,"phase",phase);cJSON_AddNumberToObject(e,"status",status);
    ezb_extaddr_t local;ezb_get_extended_address(&local);char dest[17];snprintf(dest,sizeof(dest),"%016" PRIx64,local.u64);
    cJSON_AddStringToObject(e,"coordinator_ieee",dest);cJSON_AddNumberToObject(e,"coordinator_endpoint",10);
    if(p->has_tsn)cJSON_AddNumberToObject(e,"tsn",p->tsn);
    return e;
}
static pending_t *lookup(uintptr_t token)
{for(int i=0;i<SLOTS;i++)if(pending[i].used&&pending[i].token==token)return &pending[i];return NULL;}
static void bind_cb(const ezb_zdp_bind_req_result_t *r,void *ctx)
{
    pending_t *p=lookup((uintptr_t)ctx);if(!p)return;
    gateway_emit(result(p,r->error==EZB_ERR_NONE&&r->rsp?"response":"transport_error",r->rsp?r->rsp->status:r->error));p->used=false;
}
static void confirm(ezb_af_user_cnf_t *cnf,void *ctx)
{
    pending_t *p=lookup((uintptr_t)ctx);if(!p)return;
    p->tsn=cnf->tsn;p->has_tsn=true;
    if(cnf->status){gateway_emit(result(p,"transport_error",cnf->status));p->used=false;}
}
ezb_err_t gateway_reporting_command(const cJSON *o,uint64_t ieee,uint16_t nwk)
{
    const char *op=cJSON_GetObjectItemCaseSensitive(o,"op")->valuestring;
    if(!strncmp(op,"plug_",5)&&!plug_allowed(nwk,cJSON_GetObjectItemCaseSensitive(o,"endpoint")->valueint))return EZB_ERR_FAIL;
    if(!strcmp(op,"reporting_window")){
        int seconds=cJSON_GetObjectItemCaseSensitive(o,"seconds")->valueint;int64_t now=esp_timer_get_time();
        for(int i=0;i<SLOTS;i++)if(windows[i].nwk==nwk||windows[i].until<=now){windows[i]=(window_t){nwk,now+seconds*1000000LL};return EZB_ERR_NONE;}
        return EZB_ERR_NO_MEM;
    }
    pending_t *p=NULL;
    /* One operation per source/cluster avoids ambiguous response correlation. */
    int cluster=cJSON_GetObjectItemCaseSensitive(o,"cluster")->valueint;
    for(int i=0;i<SLOTS;i++){if(pending[i].used&&pending[i].nwk==nwk&&pending[i].cluster==cluster)return EZB_ERR_FAIL;if(!pending[i].used)p=&pending[i];}
    if(!p)return EZB_ERR_NO_MEM;
    *p=(pending_t){.used=true,.token=++next_token,.ieee=ieee,.nwk=nwk,.ep=cJSON_GetObjectItemCaseSensitive(o,"endpoint")->valueint,.cluster=cluster,.attribute=cJSON_GetObjectItemCaseSensitive(o,"attribute")?cJSON_GetObjectItemCaseSensitive(o,"attribute")->valueint:0,.deadline=esp_timer_get_time()+TIMEOUT_US};
    strcpy(p->op,op);strcpy(p->id,cJSON_GetObjectItemCaseSensitive(o,"request_id")->valuestring);
    ezb_err_t err;
    if(!strcmp(op,"bind")||!strcmp(op,"plug_bind")){
        ezb_zdo_bind_req_t req={.dst_nwk_addr=nwk,.field={.src_addr.u64=ieee,.src_ep=p->ep,.cluster_id=cluster,.dst_addr_mode=3,.dst_ep=10},.cb=bind_cb,.user_ctx=(void *)p->token};
        ezb_get_extended_address(&req.field.dst_addr.extended_addr);
        err=ezb_zdo_bind_req(&req);
    }else{
        ezb_zcl_cmd_ctrl_t ctrl={.dst_addr={.addr_mode=EZB_ADDR_MODE_SHORT,.u.short_addr=nwk},.dst_ep=p->ep,.src_ep=10,.cluster_id=cluster,.cnf_ctx={.cb=confirm,.user_ctx=(void *)p->token}};
        if(!strncmp(op,"plug_",5)){
            if(!strcmp(op,"plug_relay")){
                ezb_zcl_on_off_cmd_t cmd={.cmd_ctrl={.dst_addr=ctrl.dst_addr,.dst_ep=ctrl.dst_ep,.src_ep=ctrl.src_ep,.cnf_ctx=ctrl.cnf_ctx}};err=cJSON_GetObjectItemCaseSensitive(o,"value")->valueint?ezb_zcl_on_off_on_cmd_req(&cmd):ezb_zcl_on_off_off_cmd_req(&cmd);
            }else if(!strcmp(op,"plug_inching")){
                uint8_t b[29];size_t n;plug_payload(o,b,&n);ctrl.manuf_code=0x1286;ctrl.fc.manuf_specific=1;
                ezb_zcl_custom_cluster_cmd_t cmd={.cmd_ctrl=ctrl,.cmd_id=1,.data_length=n,.data=b};err=ezb_zcl_custom_cluster_cmd_req(&cmd);
            }else if(!strcmp(op,"plug_write")){
                uint8_t b[30]={0};size_t n;int type=gateway_plug_type(cluster,p->attribute);
                if(type==0x42){plug_payload(o,b+1,&n);b[0]=n;}else {b[0]=cJSON_GetObjectItemCaseSensitive(o,"value")->valueint;n=0;}
                ezb_zcl_attribute_t attr={.id=p->attribute,.data={.type=type,.size=type==0x42?n+1:1,.value=b}};
                ezb_zcl_write_attr_cmd_t cmd={.cmd_ctrl=ctrl,.payload={.attr_number=1,.attr_field=&attr}};err=ezb_zcl_write_attr_cmd_req(&cmd);
            }else if(!strcmp(op,"plug_read")){
                uint16_t attr=p->attribute;ezb_zcl_read_attr_cmd_t cmd={.cmd_ctrl=ctrl,.payload={.attr_number=1,.attr_field=&attr}};err=ezb_zcl_read_attr_cmd_req(&cmd);
            }else if(!strcmp(op,"plug_configure")){
                int type,min,max;uint64_t change;gateway_plug_report(cluster,p->attribute,&type,&min,&max,&change);
                ezb_zcl_config_report_record_t record={.direction=0,.attr_id=p->attribute,.client={.attr_type=type,.min_interval=min,.max_interval=max}};
                memcpy(&record.client.reportable_change,&change,type==0x25?6:type==0x23?4:1);
                ezb_zcl_config_report_cmd_t cmd={.cmd_ctrl=ctrl,.payload={.record_number=1,.record_field=&record}};err=ezb_zcl_config_report_cmd_req(&cmd);
            }else{
                ezb_zcl_read_report_config_record_t record={.report_direction=0,.attr_id=p->attribute};ezb_zcl_read_report_config_cmd_t cmd={.cmd_ctrl=ctrl,.payload={.record_number=1,.record_field=&record}};err=ezb_zcl_read_report_config_cmd_req(&cmd);
            }
        }else if(!strcmp(op,"write_display")||!strcmp(op,"read_display")){
            /* These upstream scalar writes use standard manufacturer framing on
             * vendor cluster FC11. Do not apply weather-command framing to them. */
            if(!strcmp(op,"write_display")){
                int type,low,high;gateway_display_spec(p->attribute,&type,&low,&high);
                uint16_t value=(uint16_t)cJSON_GetObjectItemCaseSensitive(o,"value")->valueint;
                ezb_zcl_attribute_t attr={.id=p->attribute,.data={.type=type,.size=2,.value=&value}};
                ezb_zcl_write_attr_cmd_t cmd={.cmd_ctrl=ctrl,.payload={.attr_number=1,.attr_field=&attr}};err=ezb_zcl_write_attr_cmd_req(&cmd);
            }else{
                uint16_t attr=p->attribute;ezb_zcl_read_attr_cmd_t cmd={.cmd_ctrl=ctrl,.payload={.attr_number=1,.attr_field=&attr}};err=ezb_zcl_read_attr_cmd_req(&cmd);
            }
        }else if(!strcmp(op,"configure_reporting")){
            ezb_zcl_config_report_record_t record={.direction=0,.attr_id=p->attribute,.client={.attr_type=cluster==0x402?0x29:cluster==1?0x20:0x21,.min_interval=cJSON_GetObjectItemCaseSensitive(o,"min_interval")->valueint,.max_interval=cJSON_GetObjectItemCaseSensitive(o,"max_interval")->valueint}};
            record.client.reportable_change.u16=cJSON_GetObjectItemCaseSensitive(o,"reportable_change")->valueint;
            ezb_zcl_config_report_cmd_t cmd={.cmd_ctrl=ctrl,.payload={.record_number=1,.record_field=&record}};err=ezb_zcl_config_report_cmd_req(&cmd);
        }else{
            ezb_zcl_read_report_config_record_t record={.report_direction=0,.attr_id=p->attribute};
            ezb_zcl_read_report_config_cmd_t cmd={.cmd_ctrl=ctrl,.payload={.record_number=1,.record_field=&record}};err=ezb_zcl_read_report_config_cmd_req(&cmd);
        }
    }
    if(err!=EZB_ERR_NONE)p->used=false;
    return err;
}
static pending_t *match(const ezb_zcl_cmd_hdr_t *h,const char *op)
{
    if(!h||h->src_addr.addr_mode!=EZB_ADDR_MODE_SHORT||h->dst_ep!=10)return NULL;
    for(int i=0;i<SLOTS;i++){pending_t *p=&pending[i];if(p->used&&p->has_tsn&&gateway_reporting_response_matches((gateway_reporting_source_t){p->nwk,p->cluster,p->ep,p->tsn},(gateway_reporting_source_t){h->src_addr.u.short_addr,h->cluster_id,h->src_ep,h->tsn})&&(!op||!strcmp(p->op,op)))return p;}
    return NULL;
}
void gateway_reporting_action(ezb_zcl_core_action_callback_id_t id,void *message)
{
    if(id==EZB_ZCL_CORE_WRITE_ATTR_RSP_CB_ID){
        ezb_zcl_cmd_write_attr_rsp_message_t *m=message;pending_t *p=match(m->in.header,NULL);
        if(p&&strcmp(p->op,"write_display")&&strcmp(p->op,"plug_write"))p=NULL;
        if(p&&m->in.variables){gateway_emit(result(p,"response",m->in.variables->status));p->used=false;}
    }else if(id==EZB_ZCL_CORE_READ_ATTR_RSP_CB_ID){
        ezb_zcl_cmd_read_attr_rsp_message_t *m=message;pending_t *p=match(m->in.header,NULL);
        if(p&&strcmp(p->op,"read_display")&&strcmp(p->op,"plug_read"))p=NULL;
        if(p)for(ezb_zcl_read_attr_rsp_variable_t *v=m->in.variables;v;v=v->next)if(v->attr_id==p->attribute){
            cJSON *e=result(p,"response",v->status);
            if(v->status==0&&v->attr_value&&!strcmp(p->op,"plug_read")){
                cJSON_AddNumberToObject(e,"data_type",v->attr_type);uint64_t raw=0;
                int size=v->attr_type==0x25?6:v->attr_type==0x23?4:v->attr_type==0x22?3:1;
                if(v->attr_type==0x42){uint8_t *b=v->attr_value;char hex[59];if(b[0]<=29){for(int k=0;k<b[0];k++)snprintf(hex+2*k,3,"%02x",b[k+1]);hex[2*b[0]]=0;cJSON_AddStringToObject(e,"raw_hex",hex);}}
                else {memcpy(&raw,v->attr_value,size);cJSON_AddNumberToObject(e,"raw",(double)raw);}
            }else if(v->status==0&&v->attr_value&&(v->attr_type==0x29||v->attr_type==0x21)){
                uint16_t value;memcpy(&value,v->attr_value,2);cJSON_AddNumberToObject(e,"raw",v->attr_type==0x29?(int16_t)value:value);cJSON_AddNumberToObject(e,"data_type",v->attr_type);
            }gateway_emit(e);p->used=false;break;
        }
    }else if(id==EZB_ZCL_CORE_CONFIG_REPORT_RSP_CB_ID){
        ezb_zcl_cmd_config_report_rsp_message_t *m=message;pending_t *p=match(m->in.header,NULL);
        if(p&&strcmp(p->op,"configure_reporting")&&strcmp(p->op,"plug_configure"))p=NULL;
        if(p&&m->in.variables){gateway_emit(result(p,"response",m->in.variables->status));p->used=false;}
    }else if(id==EZB_ZCL_CORE_READ_REPORT_CONFIG_RSP_CB_ID){
        ezb_zcl_cmd_read_report_config_rsp_message_t *m=message;pending_t *p=match(m->in.header,NULL);
        if(p&&strcmp(p->op,"read_reporting")&&strcmp(p->op,"plug_read_reporting"))p=NULL;
        if(p)for(ezb_zcl_read_report_config_rsp_variable_t *v=m->in.variables;v;v=v->next)if(v->attr_id==p->attribute&&v->direction==0){
            cJSON *e=result(p,"response",v->status);
            if(v->status==0){cJSON_AddNumberToObject(e,"data_type",v->client.attr_type);cJSON_AddNumberToObject(e,"min_interval",v->client.min_interval);cJSON_AddNumberToObject(e,"max_interval",v->client.max_interval);uint64_t delta=0;memcpy(&delta,&v->client.delta,v->client.attr_type==0x25?6:v->client.attr_type==0x23?4:p->cluster==1||p->cluster==6?1:2);cJSON_AddNumberToObject(e,"reportable_change",(double)delta);}
            gateway_emit(e);p->used=false;break;
        }
    }else if(id==EZB_ZCL_CORE_DEFAULT_RSP_CB_ID){
        ezb_zcl_cmd_default_rsp_message_t *m=message;pending_t *p=match(m->in.header,NULL);
        if(p&&(m->in.status_code||!strcmp(p->op,"plug_relay")||!strcmp(p->op,"plug_inching"))){gateway_emit(result(p,"response",m->in.status_code));p->used=false;}
    }else if(id==EZB_ZCL_CORE_POLL_CONTROL_CHECK_IN_CB_ID){
        ezb_zcl_poll_control_check_in_message_t *m=message;const ezb_zcl_cmd_hdr_t *h=m->in.header;
        m->out.result=0;m->out.start_fast_poll=false;m->out.fast_poll_timeout=0;
        if(h&&h->src_addr.addr_mode==EZB_ADDR_MODE_SHORT){
            int64_t now=esp_timer_get_time();for(int i=0;i<SLOTS;i++)if(windows[i].nwk==h->src_addr.u.short_addr&&windows[i].until>now){m->out.start_fast_poll=true;m->out.fast_poll_timeout=120;break;}
            cJSON *e=cJSON_CreateObject();cJSON_AddStringToObject(e,"type","check_in");cJSON_AddNumberToObject(e,"nwk",h->src_addr.u.short_addr);cJSON_AddNumberToObject(e,"endpoint",h->src_ep);cJSON_AddBoolToObject(e,"fast_poll",m->out.start_fast_poll);gateway_emit(e);
        }
    }
}
static void expire_task(void *arg)
{
    (void)arg;
    for(;;){vTaskDelay(pdMS_TO_TICKS(1000));if(!esp_zigbee_lock_acquire(pdMS_TO_TICKS(100)))continue;
        gateway_clock_update();int64_t now=esp_timer_get_time();for(int i=0;i<SLOTS;i++)if(pending[i].used&&gateway_reporting_expired(now,pending[i].deadline)){gateway_emit(result(&pending[i],"timeout",-1));pending[i].used=false;}
        esp_zigbee_lock_release();
    }
}
void gateway_reporting_init(void)
{configASSERT(xTaskCreate(expire_task,"report_expiry",4096,NULL,3,NULL)==pdPASS);}
