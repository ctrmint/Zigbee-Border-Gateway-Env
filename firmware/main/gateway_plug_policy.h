/* SPDX-License-Identifier: MIT
 * SONOFF S60ZBTPG policy. Evidence pinned in docs/S60ZBTPG.md. */
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
static inline int gateway_plug_type(int c,int a)
{
    if(c==6)return a==0?0x10:a==0x4003?0x30:-1;
    if(c==0x702)return a==0?0x25:a==0x300?0x30:(a==0x301||a==0x302)?0x22:-1;
    if(c!=0xfc11)return -1;
    if(a==1)return 0x10;
    if(a==0x7007)return 0x20;
    if(a==0x7003)return 0x42;
    if(a==0x7004||a==0x7005||a==0x7006||a==0x7009||a==0x700a||a==0x700b)return 0x23;
    return -1;
}
static inline bool gateway_plug_writable(int c,int a,int v)
{return (c==6&&a==0x4003&&(v==0||v==1||v==2||v==255))||(c==0xfc11&&(a==1||a==0x7007)&&(v==0||v==1));}
static inline bool gateway_plug_report(int c,int a,int *type,int *min,int *max,uint64_t *change)
{
    *type=gateway_plug_type(c,a);*max=3600;*min=60;*change=1;
    if(c==6&&a==0){*min=1;*max=1800;*change=0;return true;}
    if(c==0x702&&a==0)return true;
    if(c==0xfc11&&*type==0x23){*min=a<=0x7006?10:60;*change=a==0x7004?2:a>=0x7009?50:0;return true;}
    return false;
}
static inline uint32_t gateway_plug_u32(const uint8_t *b)
{return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);}
static inline bool gateway_plug_protection(const uint8_t *b,size_t n)
{
    if(n<13||n>29||b[0]!=4||b[1]!=n-2||(b[2]!=1&&b[2]!=3)||b[3]>3||(b[4]!=1&&b[4]!=3))return false;
    size_t i=5;
    for(int metric=0;metric<3;metric++){
        uint32_t hi=0,lo=0;
        for(int side=0;side<2;side++)if(b[2+metric]&(1<<side)){
            if(i+4>n)return false;
            uint32_t v=gateway_plug_u32(b+i);i+=4;
            if(metric==1?(v<165000||v>277000||v%1000):(v<100||v>(metric==0?13000u:3250000u)||v%100))return false;
            if(side==0)hi=v;else lo=v;
        }
        if(hi&&lo&&lo>=hi)return false;
    }
    return i==n;
}
static inline bool gateway_plug_inching(const uint8_t *b,size_t n)
{
    if(n!=11||b[0]!=1||b[1]!=0x17||b[2]!=7||b[3]!=0x80||(b[4]&~0x81)||b[5]||b[8]||b[9])return false;
    unsigned ticks=b[6]|((unsigned)b[7]<<8);uint8_t x=0;
    for(size_t i=0;i<n;i++)x^=b[i];
    return ticks>=1&&ticks<=7199&&x==0;
}
