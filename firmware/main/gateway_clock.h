/* SPDX-License-Identifier: MIT */
#pragma once
#include "gateway_api.h"
#include "cJSON.h"
bool gateway_clock_valid_command(const cJSON *o);
void gateway_clock_sync(const cJSON *o);
bool gateway_clock_is_valid(void);
void gateway_clock_add(ezb_af_ep_desc_t endpoint);
void gateway_clock_update(void);
void gateway_clock_register(void);
