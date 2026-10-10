#pragma once
#include "esp_zigbee.h"
#include "ezbee/zha.h"
esp_err_t gateway_api_init(void);
void gateway_ready(void);
void gateway_announce(const ezb_zdo_signal_device_annce_params_t *p);
void gateway_leave(uint16_t addr);
void gateway_zcl_action(ezb_zcl_core_action_callback_id_t id, void *message);
esp_err_t gateway_api_start(void);
