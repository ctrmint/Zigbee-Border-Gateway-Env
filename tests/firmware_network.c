#include <assert.h>
#include "gateway_network_policy.h"
int main(void){
    uint64_t now=0;uint32_t failures=0;
    for(unsigned i=0;i<100000;i++){
        failures=gw_net_increment(failures);uint32_t delay=gw_net_backoff_ms(failures,i*17);
        assert(delay>=1000 && delay<=31000);uint64_t deadline=now+delay;
        assert(!gw_net_due(now,deadline));assert(gw_net_due(deadline,deadline));now=deadline;
    }
    assert(now>7ull*24*3600*1000);assert(gw_net_increment(UINT32_MAX)==UINT32_MAX);
    assert(gw_net_backoff_ms(UINT32_MAX,0)==30000);
    assert(!gw_net_escalate(2,1000000,0));assert(!gw_net_escalate(3,119999,0));assert(gw_net_escalate(3,120000,0));
    bool connecting=true,online=false;uint64_t next=0;failures=0;
    assert(gw_net_disconnected(&connecting,&online,&failures,&next,100,0));
    assert(!connecting && !online && failures==1 && next==1100);
    assert(!gw_net_disconnected(&connecting,&online,&failures,&next,101,0));
    assert(failures==1 && next==1100);
    connecting=true;assert(gw_net_disconnected(&connecting,&online,&failures,&next,1100,0));
    assert(failures==2 && next==3100);
    assert(gw_net_can_reboot(false,0));assert(!gw_net_can_reboot(true,899999));assert(gw_net_can_reboot(true,900000));
    return 0;
}
