#pragma once
#include "esp_err.h"
#include "cJSON.h"
esp_err_t gateway_network_start(void);
void gateway_network_health(cJSON *health);
/* Authenticated, opt-in fault injection, consumed only by the network worker. */
esp_err_t gateway_network_test(const cJSON *command);
