# Device compatibility and first pairing

The gateway implements network commissioning, descriptor discovery and selected SONOFF adapters; it is not a universal driver database. WD/LD/UL sensor reports and three S60ZBTPG plugs have been observed. Consult the [dated hardware record](HARDWARE_VALIDATION_2026-10-18.md) for model/firmware-specific evidence and remaining acceptance.

| Device feature | Current support |
| --- | --- |
| Active endpoints, profile/device IDs, input/output clusters | Automatic on announcement; manual rediscovery available |
| Standard On/Off cluster 0x0006 | Explicit On/Off commands; attribute read/report state |
| Temperature 0x0402 and humidity 0x0405 | Reads/reports; SBC normalization |
| Manufacturer/model/build Basic attributes | Descriptor discovery reads attributes 4/5/0x4000; explicit reads remain available |
| Other attribute values | Supported raw ZCL types retained; uint24/uint48 supported, with semantics only for implemented sources |
| Reporting configuration / remote binding | Bounded sensor/Poll Control and identified S60ZBTPG commissioning, with correlated responses and reporting readback |
| IAS contact/motion sensors and enrolment | Not implemented |
| Manufacturer-specific support | Selected SNZB-02UL scalar settings and S60ZBTPG metering/settings; arbitrary vendor writes and Tuya data points are not implemented |
| Electrical measurement/metering | Identified S60ZBTPG FC11 electrical/period-energy scaling and standard 0702 uint48 energy with observed electricity unit and uint24 multiplier/divisor; no universal 0x0B04 adapter |
| Install-code provisioning | Not implemented; SDK default commissioning policy retained |

The gateway registers endpoint 10 with Basic, On/Off, temperature, humidity, Power Configuration, Poll Control, Metering and SONOFF vendor-cluster clients, plus its bounded Time service. A sensor’s protocol On/Off binding does not expose appliance switching controls. Reports must be addressed to a supported cluster at this endpoint. Some devices need a bind to coordinator IEEE/endpoint 10 plus Configure Reporting before unsolicited updates appear. The reporting workflow below performs those operations. Attribute reads can verify a standard sensor while awake. Do not claim a temperature dashboard is live until recurring reports or deliberate reads are observed.

1. Close pairing on other coordinators; factory reset the test device following its instructions.
2. Open pairing for 60 seconds in this dashboard.
3. Keep the device awake close to the gateway during commissioning and discovery.
4. Confirm an IEEE entry and successful endpoint descriptors.
5. Read the relevant attribute and inspect its type/raw value. Re-discover if a sleepy device missed the interview.
6. For a plug, read its current state/settings first. Use an ordinary test load for deliberately requested On/Off checks; do not unexpectedly interrupt an existing appliance. Identified S60ZBTPG controls use durable acknowledged/readback jobs.
7. Close pairing. Move the device to its final location and repeat checks.

A device normally belongs to one Zigbee network. Moving devices from an existing coordinator usually requires resetting/re-pairing; this repository provides no network migration tool. Fifty application registry slots do not guarantee fifty direct children or fifty compatible models. Add mains-powered routers and validate each model.

## Temperature/humidity reporting commissioning (issue #10)

The gateway now supports remote Bind, Configure Reporting and Read Reporting
Configuration for measured value attribute 0 on temperature (0x0402, int16) and
humidity (0x0405, uint16). Bindings target the coordinator's actual IEEE and client
endpoint 10. Poll Control (0x0020) is registered as a client and bound first when
advertised by the sensor. Check-ins request at most 30 seconds of fast polling
only during an explicitly armed, at most 120-second commissioning window; normal
poll intervals are not changed. Outside that window check-ins decline fast poll.

In Configuration & Setup, use **Sensor reporting setup** on a discovered, active
temperature and/or humidity endpoint. Only the measurements actually advertised
by that endpoint are configured; a temperature-only probe has no humidity field
or humidity setup steps. For the user-identified SONOFF SNZB-02WD, the initial
policy is 5-second minimum / 3,600-second maximum, 0.2°C temperature change and
1 percentage point humidity change. These follow the upstream converter's reference
settings, not a verified promise about every device firmware revision:
https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/sonoff.ts

Briefly press the device button to wake it when requested; follow the manufacturer's
manual and do not hold/reset/re-pair it. Desired policy and progress live on the Pi.
One operation is outstanding per job, with at most three attempts per step, a
27-second acknowledgement deadline, 30-second retry delay and five-minute overall
expiry. New sensor traffic can bring forward a waiting retry. Cancel stops future
attempts; in-flight Zigbee operations can still complete. Changes are idempotent.
After a gateway reboot, active/completed policies restart once with a new bounded
window; cancelled, failed and expired jobs require an explicit retry. A Pi restart
retains the pending correlation/deadline and ingests any saved response first.

`verified` means bindings/configuration were acknowledged and reporting readback
matched; it does not mean recurring reports have been observed. Unsupported
readback yields `configured_unverified`, and mismatched settings remain an error.
Read-response and unsolicited-report telemetry are separately labelled; older
measurements have origin `unknown`. Model/manufacturer reads are best effort;
user-supplied model identity remains distinct from Basic-cluster identity.

Special disabling/reset reporting intervals (maximum 0 or 65535, minimum 65535)
are deliberately rejected by this periodic-reporting policy. Values are expressed
in °C / percentage points in the dashboard and converted exactly to hundredths
for ZCL. Keep reading freshness above the maximum interval, e.g. 4,500 seconds
for an hourly heartbeat; changing freshness alone does not repair missing reports.
Battery reporting is separate from the base temperature/humidity workflow. The SNZB-02UL extension supports bounded battery reporting setup and half-percent/tenths-of-volt normalization when observed; unsupported or missing attributes remain explicit.


The Fish Tank sensor is user-identified as **SONOFF SNZB-02LD**, SONOFF's
waterproof temperature probe model. Its descriptor exposes temperature and Poll
Control, with no humidity cluster. The reference converter uses temperature
minimum 5 seconds, maximum 3600 seconds and delta 20 (0.2°C), plus Poll Control
binding. This matches the temperature-only policy. The dashboard supports an
SNZB-02LD model hint separately from Basic-cluster identity; radio verification
and recurring reporting must still be confirmed. See the
[manufacturer manual](https://support.sonoff.tech/snzb-02ld-usermanual/) and
[upstream converter](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/sonoff.ts).

## SNZB-02UL advance support

See [SNZB-02UL preparation](SNZB_02UL.md) for profile defaults, battery scaling, display APIs, firmware upgrade requirements and pending physical checks. Generated contracts include the sensor-profile/display routes and bounded gateway operations.

## S60ZBTPG smart plugs

Three exact-model SONOFF S60ZBTPG Type G units with Basic build 1.0.2 have been identified. Each completed all 34 commissioning steps, including three bindings, eight reporting configurations/readbacks and 15 initial reads. Live electrical reports, selected settings and gateway restart recovery have evidence; full period-energy, mesh path, power-cycle and OTA acceptance remains incomplete. See [plug operation/capabilities](S60ZBTPG.md) and the [hardware record](HARDWARE_VALIDATION_2026-10-18.md).
