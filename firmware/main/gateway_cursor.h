/* SPDX-License-Identifier: MIT */
#pragma once
#include <stdbool.h>
#include <stdint.h>

/* Decimal API cursors must fit uint32_t; never silently wrap or truncate. */
static inline bool gateway_parse_cursor(const char *s, uint32_t *value)
{
    if (!s || !*s) return false;
    uint32_t n = 0;
    for (; *s; ++s) {
        if (*s < '0' || *s > '9') return false;
        uint32_t digit = (uint32_t)(*s - '0');
        if (n > (UINT32_MAX - digit) / 10) return false;
        n = n * 10 + digit;
    }
    *value = n;
    return true;
}

static inline bool gateway_cursor_gap(uint32_t after, uint32_t oldest, uint32_t latest)
{
    return after < oldest - 1 || after > latest;
}

static inline uint32_t gateway_batch_end(uint32_t after, uint32_t latest)
{
    return latest - after > 16 ? after + 16 : latest;
}
