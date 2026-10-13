/* SPDX-License-Identifier: MIT */
#pragma once
#include <stdbool.h>
#include <string.h>
#include "cJSON.h"

/* Parse the whole HTTP body, including its explicit terminator. */
static inline cJSON *gateway_parse_command(const char *body, size_t length)
{
    if (!body || memchr(body, '\0', length)) return NULL;
    /* cJSON exposes C strings: escaped NULs would truncate keys/operations. */
    for (size_t i = 0; i < length; ++i) {
        if (body[i] != '\\') continue;
        if (length - i >= 6 && !memcmp(body + i, "\\u0000", 6)) return NULL;
        ++i; /* Skip the escaped character, including a literal backslash. */
    }
    cJSON *o = cJSON_ParseWithLengthOpts(body, length + 1, NULL, true);
    if (!cJSON_IsObject(o)) { cJSON_Delete(o); return NULL; }
    for (cJSON *a = o->child; a; a = a->next)
        for (cJSON *b = a->next; b; b = b->next)
            if (!strcmp(a->string, b->string)) { cJSON_Delete(o); return NULL; }
    return o;
}
