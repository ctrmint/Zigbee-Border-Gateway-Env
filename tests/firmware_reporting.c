/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include "gateway_reporting_policy.h"
int main(void)
{
    assert(gateway_reporting_policy(0x402,0,5,3600,20));
    assert(gateway_reporting_policy(0x405,0,5,3600,100));
    assert(gateway_reporting_policy(0x402,0,0,1,1));
    assert(!gateway_reporting_policy(0x402,0,5,0,20));
    assert(!gateway_reporting_policy(0x402,0,5,65535,20));
    assert(!gateway_reporting_policy(0x402,0,3601,3600,20));
    assert(!gateway_reporting_policy(0x402,0,65535,65535,20));
    assert(!gateway_reporting_policy(0x405,0,5,3600,10001));
    assert(!gateway_reporting_policy(0x402,0,5,3600,32768));
    assert(!gateway_reporting_policy(0x402,1,5,3600,20));
    assert(!gateway_reporting_policy(6,0,5,3600,20));
    assert(!gateway_reporting_policy(0x405,0,5,3600,0));
    gateway_reporting_source_t source={0x1234,0x402,1,42};
    assert(gateway_reporting_response_matches(source,source));
    assert(!gateway_reporting_response_matches(source,(gateway_reporting_source_t){0x1235,0x402,1,42}));
    assert(!gateway_reporting_response_matches(source,(gateway_reporting_source_t){0x1234,0x405,1,42}));
    assert(!gateway_reporting_response_matches(source,(gateway_reporting_source_t){0x1234,0x402,2,42}));
    assert(!gateway_reporting_response_matches(source,(gateway_reporting_source_t){0x1234,0x402,1,41}));
    assert(!gateway_reporting_expired(24999999,25000000));
    assert(gateway_reporting_expired(25000000,25000000));
    return 0;
}
