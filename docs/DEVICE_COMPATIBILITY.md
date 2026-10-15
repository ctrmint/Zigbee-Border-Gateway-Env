# Device compatibility and first pairing

This MVP implements generic network commissioning and simple-descriptor discovery, not a universal driver database. Start with one standard On/Off plug and one temperature/humidity sensor.

| Device feature | Current support |
| --- | --- |
| Active endpoints, profile/device IDs, input/output clusters | Automatic on announcement; manual rediscovery available |
| Standard On/Off cluster 0x0006 | Explicit On/Off commands; attribute read/report state |
| Temperature 0x0402 and humidity 0x0405 | Reads/reports; SBC normalization |
| Manufacturer/model Basic attributes | Manual reads of attributes 4/5 |
| Other scalar attribute values | Raw supported ZCL types copied; no semantic adapter |
| Reporting configuration / remote binding | Bounded temperature/humidity commissioning and Poll Control binding; hardware validation recorded separately |
| IAS contact/motion sensors and enrolment | Not implemented |
| Tuya data points and vendor-specific payloads | Not implemented |
| Electrical measurement/metering | No multiplier/divisor normalization or uint48 decoder |
| Install-code provisioning | Not implemented; SDK default commissioning policy retained |

The gateway registers endpoint 10 and client clusters Basic, On/Off, temperature and humidity. Reports must be addressed to a supported cluster at this endpoint. Some devices need a bind to coordinator IEEE/endpoint 10 plus Configure Reporting before unsolicited updates appear. The reporting workflow below performs those operations. Attribute reads can verify a standard sensor while awake. Do not claim a temperature dashboard is live until recurring reports or deliberate reads are observed.

1. Close pairing on other coordinators; factory reset the test device following its instructions.
2. Open pairing for 60 seconds in this dashboard.
3. Keep the device awake close to the gateway during commissioning and discovery.
4. Confirm an IEEE entry and successful endpoint descriptors.
5. Read the relevant attribute and inspect its type/raw value. Re-discover if a sleepy device missed the interview.
6. For a plug, send Off, then Read On/Off and verify physical state.
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
temperature/humidity endpoint. For the user-identified SONOFF SNZB-02WD, the initial
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
Battery percentage/voltage reporting is not part of this implementation.
