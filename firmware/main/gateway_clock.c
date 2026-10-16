/* SPDX-License-Identifier: MIT */
#include <math.h>
#include <sys/time.h>
#include <time.h>
#include "freertos/FreeRTOS.h"
#include "gateway_clock.h"
#include "gateway_sensor_policy.h"
#include "ezbee/zcl/cluster/time.h"
#include "esp_timer.h"
/* Lease expiry uses monotonic time, so a UTC adjustment cannot extend validity. */
static int64_t valid_until;
static portMUX_TYPE clock_mux=portMUX_INITIALIZER_UNLOCKED;
static int32_t utc_offset;
static ezb_zcl_cluster_desc_t cluster;
bool gateway_clock_is_valid(void){portENTER_CRITICAL(&clock_mux);int64_t until=valid_until;portEXIT_CRITICAL(&clock_mux);return until>esp_timer_get_time();}
static uint32_t utc(void){return gateway_clock_is_valid()?gateway_zigbee_time(time(NULL)):UINT32_MAX;}
static void ignore_remote_time(uint32_t value){(void)value;}
bool gateway_clock_valid_command(const cJSON *o)
{
    cJSON *stamp=cJSON_GetObjectItemCaseSensitive(o,"unix_time"),*offset=cJSON_GetObjectItemCaseSensitive(o,"utc_offset");
    return cJSON_GetArraySize(o)==3&&cJSON_IsNumber(stamp)&&isfinite(stamp->valuedouble)&&stamp->valuedouble==floor(stamp->valuedouble)&&stamp->valuedouble>=1577836800&&stamp->valuedouble<=4102444800LL&&cJSON_IsNumber(offset)&&isfinite(offset->valuedouble)&&offset->valuedouble==floor(offset->valuedouble)&&offset->valuedouble>=-50400&&offset->valuedouble<=50400;
}
static void set(uint16_t id,const void *value)
{
    ezb_zcl_attr_desc_t attr=ezb_zcl_cluster_get_attr_desc(cluster,id,EZB_ZCL_STD_MANUF_CODE);
    if(attr)ezb_zcl_attr_desc_set_value(attr,value);
}
void gateway_clock_update(void)
{
    if(!cluster)return;
    uint32_t now=utc(),local=now==UINT32_MAX?UINT32_MAX:(uint32_t)((int64_t)now+utc_offset);
    uint8_t status=gateway_clock_is_valid()?EZB_ZCL_TIME_TIME_STATUS_SYNCHRONIZED:0;
    set(0,&now);set(1,&status);set(2,&utc_offset);set(6,&local);set(7,&local);
}
void gateway_clock_sync(const cJSON *o)
{
    struct timeval tv={.tv_sec=(time_t)cJSON_GetObjectItemCaseSensitive(o,"unix_time")->valuedouble,.tv_usec=0};
    settimeofday(&tv,NULL);utc_offset=cJSON_GetObjectItemCaseSensitive(o,"utc_offset")->valueint;portENTER_CRITICAL(&clock_mux);valid_until=esp_timer_get_time()+900000000LL;portEXIT_CRITICAL(&clock_mux);
    uint32_t now=gateway_zigbee_time(tv.tv_sec),until=now+900;set(8,&now);set(9,&until);gateway_clock_update();
}
void gateway_clock_add(ezb_af_ep_desc_t endpoint)
{
    cluster=ezb_zcl_time_create_cluster_desc(NULL,EZB_ZCL_CLUSTER_SERVER);configASSERT(cluster);
    uint32_t unknown=UINT32_MAX;int32_t zero=0;
    ESP_ERROR_CHECK(ezb_zcl_time_cluster_desc_add_attr(cluster,2,&zero));
    ESP_ERROR_CHECK(ezb_zcl_time_cluster_desc_add_attr(cluster,3,&unknown));
    ESP_ERROR_CHECK(ezb_zcl_time_cluster_desc_add_attr(cluster,4,&unknown));
    ESP_ERROR_CHECK(ezb_zcl_time_cluster_desc_add_attr(cluster,5,&zero));
    for(uint16_t i=6;i<=9;i++)ESP_ERROR_CHECK(ezb_zcl_time_cluster_desc_add_attr(cluster,i,&unknown));
    ESP_ERROR_CHECK(ezb_af_endpoint_add_cluster_desc(endpoint,cluster));
}
void gateway_clock_register(void)
{
    ezb_zcl_time_interface_t interface={.get_utc_time=utc,.set_utc_time=ignore_remote_time};
    ESP_ERROR_CHECK(ezb_zcl_time_server_interface_register(10,interface));
}
