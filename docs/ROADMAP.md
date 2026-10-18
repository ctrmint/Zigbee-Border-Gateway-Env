# Roadmap

## Implemented baseline

S3/H2 hardware builds and local Zigbee coordination, persistent registry/polling, sensor reporting/readback, selected SONOFF adapters, battery/RSSI/history, per-profile dashboard layouts and metering-plug jobs are implemented. Three temperature sensors and three S60ZBTPG plugs have been connected. Selected plug switching, settings and restart recovery have actual-device evidence; this is not universal compatibility or full #27 acceptance. See [hardware validation](HARDWARE_VALIDATION_2026-10-18.md) and [automated validation](VALIDATION.md).

## Remaining work

1. Complete model/firmware-specific hardware acceptance: sustained energy accumulation and period boundaries, intended plug power-loss behavior, routing observations and physical plug UI acceptance. Keep [#27](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/27) open.
2. Implement/verify plug OTA via [#30](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/30); audit schedules/countdowns/scenes and verify device inching timing/persistence via [#31](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/31). UL remote/weather and OTA remain separately tracked in #16/#17.
3. Complete extended Wi-Fi hardware scenarios in [#28](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/28): prolonged/repeated outages, actual DHCP address changes, AP/router restart without a manual gateway reset and forced internal-stall escalation. A Pi manually power-cycled after lost access does not establish the original cause.
4. Extend adapters beyond the implemented models, including IAS Zone enrolment and generic Electrical Measurement scaling. Add general command tracking/streaming only with published schemas; existing dedicated jobs do not imply those future endpoints exist.
5. Add authenticated encrypted board transport, signed updates, tested secure storage and credential rotation without network erasure.
6. Add optional MQTT and rules with explicit stale-data, offline, restart and fail-safe semantics.
7. Implement registry deletion, secure Zigbee network backup/recovery with frame-counter handling, and larger 20–50-node/RF/coexistence/heap/discovery benchmarks. Ethernet/PTA require matching hardware validation.

Physical iPad acceptance for the earlier All/profile/RSSI/layout features is recorded in closed #18/#20/#23/#25. It does not establish acceptance of later plug controls or all possible tablet/browser versions.
