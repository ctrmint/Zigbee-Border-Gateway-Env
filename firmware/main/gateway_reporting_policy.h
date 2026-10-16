/* SPDX-License-Identifier: MIT */
#pragma once
#include <stdbool.h>
#include <stdint.h>
/* Special ZCL interval values (0/65535) are deliberately unsupported by this
 * periodic sensor policy; they must never silently disable the heartbeat. */
static inline bool gateway_reporting_policy(int cluster,int attr,int min,int max,int change)
{
    bool source=((cluster==0x0402||cluster==0x0405)&&attr==0)||(cluster==1&&(attr==32||attr==33));
    int limit=cluster==0x0402?32767:cluster==0x0405?10000:254;
    return source && min>=0 && min<=65534 && max>=1 && max<=65534 && min<=max && change>=1 && change<=limit;
}

typedef struct {uint16_t nwk,cluster;uint8_t ep,tsn;} gateway_reporting_source_t;
static inline bool gateway_reporting_response_matches(gateway_reporting_source_t expected,gateway_reporting_source_t received)
{
    return expected.nwk==received.nwk && expected.cluster==received.cluster && expected.ep==received.ep && expected.tsn==received.tsn;
}
static inline bool gateway_reporting_expired(int64_t now,int64_t deadline)
{return now>=deadline;}
