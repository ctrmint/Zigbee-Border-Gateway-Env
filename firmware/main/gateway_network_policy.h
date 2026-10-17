#pragma once
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
/* No retry ceiling. Each individual operation and delay is bounded. */
static inline uint32_t gw_net_increment(uint32_t n) { return n==UINT32_MAX?n:n+1; }
static inline uint32_t gw_net_backoff_ms(uint32_t failures, uint32_t random) {
    uint32_t shift=failures>5?5:failures?failures-1:0;
    uint32_t base=1000u<<shift;if(base>30000)base=30000;
    return base+random%1001; /* capped at 31 seconds */
}
static inline bool gw_net_due(uint64_t now, uint64_t deadline) { return now>=deadline; }
static inline bool gw_net_escalate(unsigned errors, uint64_t now, uint64_t last) {
    return errors>=3 && now>=last+120000;
}

static inline bool gw_net_disconnected(bool *connecting, bool *online, uint32_t *failures, uint64_t *next, uint64_t now, uint32_t random) {
    if(!*connecting && !*online)return false;
    *connecting=false;*online=false;*failures=gw_net_increment(*failures);
    *next=now+gw_net_backoff_ms(*failures,random);return true;
}

static inline bool gw_net_can_reboot(bool guarded, uint64_t uptime) {
    return !guarded || uptime>=900000; /* at most one restart per 15 min after a repeat fault */
}
