# Hardware validation record — 18 October 2026

This record updates the software-preparation status merged through PR #32. It separates device responses, user-observed behavior and automated tests. It is an observation record for the tested firmware, not a guarantee for every unit/version or a claim that all parent acceptance criteria are complete. Credentials, household device names/addresses, raw journals, database snapshots and flash images remain private and excluded from Git.

## Tested installation and evidence

As recorded during these checks, the installation has an ESP32-S3 gateway with ESP32-H2 RCP, three WD/LD/UL temperature sensors and three SONOFF S60ZBTPG Type G smart plugs. All three plugs returned Basic manufacturer SONOFF, model S60ZBTPG, build **1.0.2**, endpoint 1 with On/Off 0006, Metering 0702 and SONOFF FC11 server clusters. Endpoint 242 was also discovered; control/reporting jobs target endpoint 1. All six device registrations were observed without re-pairing the existing sensors.

The dashboard host identifies as **Raspberry Pi 4 Model B Rev 1.2** and is also the firmware development workstation. The host's name is not evidence of its hardware model. ESP-IDF 5.5.4 / ESP-Zigbee 2.0.4 remains the selected firmware baseline.

Private timestamped evidence contains the actual job responses, raw reports, source/image/reference hashes and before/after snapshots. The following public summary omits identifying household data:

| Check | Observed result | Scope / limit |
| --- | --- | --- |
| Exact identity and descriptors | Three S60ZBTPG units, build 1.0.2, required endpoint clusters present | Does not cover other firmware or Type F/Wi-Fi variants |
| Reporting setup | Each unit completed **34/34** steps with zero errors: three binds, eight Configure Reporting/readback pairs, 15 initial reads | Readback matched the requested types, intervals and deltas; not a long-duration soak |
| Standard energy metadata | Unit 0 (electricity), uint24 multiplier 1 / divisor 1000 and uint48 cumulative reads accepted | Zero totals were observed; sustained accumulation/rollover and period transitions remain unverified |
| Automatic electrical reports | Unsolicited SONOFF power/voltage reports and current changes observed; repeated power/voltage reports at approximately ten-second intervals in these checks | Not a guaranteed cadence for every metric under every condition |
| Physical button | User pressed one unit's button; unsolicited On state and nonzero electrical measurements followed | One observed loaded unit; no endurance or meter-accuracy calibration |
| Dashboard On/Off | User observed successful Off then On; both jobs verified acknowledgement plus matching state readback, 2/2 each | One unit; no additional agent-issued switching was needed |
| Electrical measurements under load | Nonzero current, voltage and active power reached the API/history without an explicit poll read | Plausible live telemetry, not comparison with a calibrated reference meter |
| Network indicator | One unit acknowledged LED enable and matching readback, 2/2 | No claim that every indicator mode was tested |
| Startup setting | One unit acknowledged `on` and matching 0006:4003 readback, 2/2 | Setting readback does not verify intended behavior through a controlled power-cycle |
| Protection configuration | On explicit user request, one unit verified limits **13 A / 3250 W**, then enable readback 1; relay remained On | Configuration only; no deliberate overload/trip test, no change to other units |
| Existing protection readbacks | Before that change, tested units returned enable 0 and stored thresholds 14 A / 3250 W | These observations are not safe product ratings or defaults for every firmware; application writes cap current at 13 A |
| Gateway restart | User-requested S3 restart restored its PAN/channel/registry and dashboard connection; the first plug stayed On and resumed automatic electrical reports without recommissioning | Establishes this coordinator-restart check, not every Pi/plug/router power-loss scenario |
| Plug relocation | A relocated second unit reconnected without re-pairing and produced fresh electrical/state/energy reports | Does not prove which router a sensor uses or that Garage reception improved |
| Pi access incident | User manually power-cycled the Pi after lost access; Pi/gateway/dashboard returned, database integrity passed | Initial Wi-Fi failure versus Pi lockup remains undetermined; previous-boot logs were volatile and lost |

## What remains open

[#27](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/27) remains open for sustained cumulative/period-energy behavior and boundaries, Off-state quirks across transitions, intended startup behavior through controlled plug power loss, broader restart/persistence checks, observed mesh paths and physical plug UI acceptance. Protection configuration readback is not evidence of an actual trip, and no unsafe overload test is required. Inching-disable acknowledgement was observed on one unit; timed execution/persistence is not verified.

OTA remains unavailable in [#30](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/30). Schedules/countdowns/scenes and actual inching timing/persistence remain in [#31](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/31). The gateway's extended Wi-Fi/DHCP/router/internal-stall scenarios remain in [#28](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/28). The separate, previously recorded 180-second same-boot network test is the autonomous recovery evidence; manual Pi power-cycling does not establish that result or the original failure's cause.

Runtime profile capability metadata still uses conservative static `prepared`/`not_tested` declarations. This documentation records subsequent scoped evidence; it does not silently change software capability gates or create a live certification status.

## Physical iPad acceptance

The user confirmed iPad acceptance and requested closure of the earlier All, profile, signal and layout issues: [#18](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/18), [#20](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/20), [#23](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/23), [#25](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/25). Those are closed. No iPad model, iPadOS/Safari version or detailed gesture/orientation/chart checklist was supplied; none is inferred. This acceptance predates the plug work and does not establish physical Safari acceptance of the new plug controls. The three plug WebKit iPad-emulation cases remain separate automated evidence.

## Software/deployment baseline

The #27 build passed 88 API/integration tests, native C sanitizer checks, SDK compilation (0x115530-byte S3 application, 35% partition free), 26 distinct Chromium cases across runs and three final WebKit iPad-emulation cases. One profile reload fetch failure passed its targeted rerun; this is not represented as a single clean combined browser run. Live read-only desktop/tablet/mobile checks showed the real devices without fake simulator entries. Full flash and SQLite backups were retained privately; only the S3 application partition was flashed, preserving bootloader/partition/NVS/H2 and the existing network. Those deployment results remain historical; this documentation update performs no restart, flash, network configuration or plug action.
