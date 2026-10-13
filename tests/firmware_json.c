/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include "gateway_json.h"

int main(void)
{
    const char *valid = " {\"op\":\"permit_join\",\"seconds\":60} \n";
    cJSON *o = gateway_parse_command(valid, strlen(valid));
    assert(o);
    assert(!strcmp(cJSON_GetObjectItemCaseSensitive(o, "op")->valuestring, "permit_join"));
    cJSON_Delete(o);
    const char *invalid[] = {"", "null", "[]", "true", "{", "{}junk", "{}{}",
        "{\"op\":\"permit_join\",\"op\":\"on_off\"}",
        "{\"seconds\":0,\"seconds\":180}",
        "{\"op\":\"read\",\"\\u006fp\":\"on_off\"}",
        "{\"op\":\"permit_join\\u0000junk\",\"seconds\":180}",
        "{\"op\\u0000junk\":\"permit_join\",\"seconds\":180}"};
    for (unsigned i = 0; i < sizeof(invalid)/sizeof(invalid[0]); ++i)
        assert(!gateway_parse_command(invalid[i], strlen(invalid[i])));
    const char embedded[] = "{}\0{\"op\":\"permit_join\"}";
    assert(!gateway_parse_command(embedded, sizeof(embedded)-1));
    const char *literal = "{\"op\":\"discover\",\"extra\":\"\\\\u0000\"}";
    o = gateway_parse_command(literal, strlen(literal));
    assert(o);
    cJSON_Delete(o);
    return 0;
}
