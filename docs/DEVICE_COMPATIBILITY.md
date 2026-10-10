# Device compatibility and first pairing

This MVP implements generic network commissioning and simple-descriptor discovery, not a universal driver database. Start with one standard On/Off plug and one temperature/humidity sensor.

| Device feature | Current support |
| --- | --- |
| Active endpoints, profile/device IDs, input/output clusters | Automatic on announcement; manual rediscovery available |
| Standard On/Off cluster 0x0006 | Explicit On/Off commands; attribute read/report state |
| Temperature 0x0402 and humidity 0x0405 | Reads/reports; SBC normalization |
| Manufacturer/model Basic attributes | Manual reads of attributes 4/5 |
| Other scalar attribute values | Raw supported ZCL types copied; no semantic adapter |
| Reporting configuration / remote binding | Not implemented; pairing alone does not establish reporting |
| IAS contact/motion sensors and enrolment | Not implemented |
| Tuya data points and vendor-specific payloads | Not implemented |
| Electrical measurement/metering | No multiplier/divisor normalization or uint48 decoder |
| Install-code provisioning | Not implemented; SDK default commissioning policy retained |

The gateway registers endpoint 10 and client clusters Basic, On/Off, temperature and humidity. Reports must be addressed to a supported cluster at this endpoint. Some devices need a bind to coordinator IEEE/endpoint 10 plus Configure Reporting before unsolicited updates appear. Those operations are future work in this API. Attribute reads can verify a standard sensor while awake. Do not claim a temperature dashboard is live until recurring reports or deliberate reads are observed.

1. Close pairing on other coordinators; factory reset the test device following its instructions.
2. Open pairing for 60 seconds in this dashboard.
3. Keep the device awake close to the gateway during commissioning and discovery.
4. Confirm an IEEE entry and successful endpoint descriptors.
5. Read the relevant attribute and inspect its type/raw value. Re-discover if a sleepy device missed the interview.
6. For a plug, send Off, then Read On/Off and verify physical state.
7. Close pairing. Move the device to its final location and repeat checks.

A device normally belongs to one Zigbee network. Moving devices from an existing coordinator usually requires resetting/re-pairing; this repository provides no network migration tool. Fifty application registry slots do not guarantee fifty direct children or fifty compatible models. Add mains-powered routers and validate each model.
