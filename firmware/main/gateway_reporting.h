/* SPDX-License-Identifier: MIT */
#pragma once
#include "gateway_api.h"
#include "cJSON.h"
bool gateway_reporting_operation(const char *op);
bool gateway_reporting_valid(const cJSON *o);
ezb_err_t gateway_reporting_command(const cJSON *o,uint64_t ieee,uint16_t nwk);
void gateway_reporting_action(ezb_zcl_core_action_callback_id_t id,void *message);
void gateway_reporting_init(void);
/* Called with Zigbee lock held; events are copied into the bounded ring. */
void gateway_emit(cJSON *event);

void gateway_plug_observe(uint16_t nwk,uint8_t ep,uint16_t attr,uint8_t type,const void *value);
void gateway_plug_forget(uint16_t nwk);
