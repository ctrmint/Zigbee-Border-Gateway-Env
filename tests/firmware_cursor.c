/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include "gateway_cursor.h"

int main(void)
{
    uint32_t n = 17;
    assert(gateway_parse_cursor("0", &n) && n == 0);
    assert(gateway_parse_cursor("4294967295", &n) && n == UINT32_MAX);
    const char *invalid[] = {"", "-1", "+1", " 1", "1 ", "1junk",
        "4294967296", "999999999999999999999", "0&after=1"};
    for (unsigned i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i)
        assert(!gateway_parse_cursor(invalid[i], &n));
    assert(!gateway_cursor_gap(0, 1, 0));
    assert(gateway_cursor_gap(UINT32_MAX, 1, 0));
    assert(gateway_cursor_gap(35, 37, 100));
    assert(!gateway_cursor_gap(36, 37, 100));
    assert(gateway_batch_end(36, 100) == 52);
    assert(gateway_batch_end(99, 100) == 100);
    assert(gateway_batch_end(UINT32_MAX, UINT32_MAX) == UINT32_MAX);
    assert(gateway_batch_end(UINT32_MAX-20, UINT32_MAX) == UINT32_MAX-4);
    assert(gateway_batch_end(UINT32_MAX-2, UINT32_MAX) == UINT32_MAX);
    return 0;
}
