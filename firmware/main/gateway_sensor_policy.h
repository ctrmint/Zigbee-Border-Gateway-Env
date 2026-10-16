/* SPDX-License-Identifier: MIT */
#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#define GATEWAY_ZIGBEE_EPOCH 946684800LL
static inline bool gateway_display_spec(int attribute,int *type,int *low,int *high)
{
    switch(attribute){
    case 3:case 4:*type=0x29;*low=0;*high=5000;break;
    case 5:case 6:*type=0x21;*low=500;*high=9500;break;
    case 7:*type=0x21;*low=0;*high=1;break;
    case 0x2003:case 0x2004:*type=0x29;*low=-5000;*high=5000;break;
    default:return false;
    }return true;
}
static inline bool gateway_display_value(int attribute,int value)
{
    int type,low,high;
    return gateway_display_spec(attribute,&type,&low,&high)&&value>=low&&value<=high&&(attribute==7||value%10==0);
}
static inline uint32_t gateway_zigbee_time(int64_t unix_time)
{return unix_time<GATEWAY_ZIGBEE_EPOCH||unix_time-GATEWAY_ZIGBEE_EPOCH>=UINT32_MAX?UINT32_MAX:(uint32_t)(unix_time-GATEWAY_ZIGBEE_EPOCH);}
