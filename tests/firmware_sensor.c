/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include "gateway_sensor_policy.h"
#include "gateway_reporting_policy.h"
int main(void)
{
    assert(gateway_display_value(7,0));assert(gateway_display_value(7,1));
    assert(!gateway_display_value(7,2));assert(!gateway_display_value(0x601e,1));
    assert(gateway_display_value(4,1800));assert(!gateway_display_value(4,1801));
    assert(gateway_display_value(0x2003,-5000));assert(!gateway_display_value(0x2003,-5010));
    assert(!gateway_display_value(5,499));assert(gateway_display_value(6,9500));
    assert(gateway_zigbee_time(946684800LL)==0);assert(gateway_zigbee_time(946684799LL)==UINT32_MAX);
    assert(gateway_zigbee_time(946684800LL+UINT32_MAX)==UINT32_MAX);
    assert(gateway_zigbee_time(1792069000LL)==845384200U);
    assert(gateway_reporting_policy(1,33,3600,21600,2));
    assert(gateway_reporting_policy(1,32,3600,21600,1));
    assert(!gateway_reporting_policy(1,0,5,1800,1));
    assert(!gateway_reporting_policy(1,33,5,1800,255));
    return 0;
}
