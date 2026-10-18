/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <string.h>
#include "gateway_plug_policy.h"
int main(void)
{
    /* Golden vectors independently checked against the pinned source framing. */
    uint8_t protect[]={4,11,1,0,1,0xc8,0x32,0,0,0x50,0x97,0x31,0};
    assert(gateway_plug_protection(protect,sizeof protect));
    for(size_t n=0;n<sizeof protect;n++)assert(!gateway_plug_protection(protect,n));
    protect[5]=0xb0;protect[6]=0x36;assert(!gateway_plug_protection(protect,sizeof protect)); /* 14 A */
    protect[5]=0xc8;protect[6]=0x32;protect[1]++;assert(!gateway_plug_protection(protect,sizeof protect));
    uint8_t inch[]={1,23,7,128,128,0,1,0,0,0,0};
    for(size_t i=0;i<10;i++)inch[10]^=inch[i];
    assert(gateway_plug_inching(inch,sizeof inch));
    for(size_t i=0;i<sizeof inch;i++){inch[i]^=1;assert(!gateway_plug_inching(inch,sizeof inch));inch[i]^=1;}
    assert(gateway_plug_type(0x702,0)==0x25);assert(gateway_plug_type(0x702,0x301)==0x22);
    assert(gateway_plug_type(0xfc11,0x7004)==0x23);assert(gateway_plug_type(0xfc11,7)==-1);
    assert(gateway_plug_writable(6,0x4003,255));assert(!gateway_plug_writable(6,0x4003,3));assert(!gateway_plug_writable(0xfc11,0x7004,1));
    int type,min,max;uint64_t change;
    assert(gateway_plug_report(6,0,&type,&min,&max,&change)&&type==0x10&&min==1&&max==1800&&change==0);
    assert(gateway_plug_report(0x702,0,&type,&min,&max,&change)&&type==0x25&&change==1);
    assert(gateway_plug_report(0xfc11,0x7009,&type,&min,&max,&change)&&type==0x23&&min==60&&change==50);
    assert(!gateway_plug_report(0xfc11,1,&type,&min,&max,&change));
    return 0;
}
