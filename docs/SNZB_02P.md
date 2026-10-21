# SONOFF SNZB-02P temperature and humidity sensor

## Support status

Gateway and dashboard software support is implemented for the SNZB-02P.
Automated tests use a synthetic Zigbee fixture. No SNZB-02P has yet been paired
with the project gateway, so radio compatibility, report cadence, battery
behavior, and restart recovery remain **hardware verification pending**.

The profile identifies a device from its Zigbee Basic-cluster manufacturer and
model strings (`SONOFF` / `SNZB-02P`). It uses standard temperature (0x0402),
relative humidity (0x0405), Power Configuration battery (0x0001), and Poll
Control (0x0020) clusters when those are advertised by the endpoint. Missing
attributes stay missing; the gateway does not create humidity, battery, or
voltage readings from a model selection alone. Temperature, humidity, battery,
available signal measurements, and their history use the existing sensor and
dashboard paths. The device has no appliance controls in the dashboard.

## Pair and configure reporting

1. Open **Configuration & Setup → Devices** and start the bounded pairing
   window.
2. Follow the [SONOFF manual](https://support.sonoff.tech/snzb-02p-usermanual/)
   to put the sensor into pairing mode. The manual describes holding its button
   for five seconds; release once the pairing indicator begins.
3. Confirm the registered device reports Basic-cluster identity `SONOFF` and
   `SNZB-02P`, then use **Discover** if its endpoint or clusters are incomplete.
4. Assign a location and use **Sensor reporting setup**. The prefilled policy
   is a project recommendation (5-second minimum, 3,600-second maximum,
   0.2°C temperature change, 1% RH change); it is configurable. Wake the sensor
   with a brief button press if it does not acknowledge commissioning.
5. Treat a `verified` reporting job as acknowledgement/readback of setup only.
   Confirm unsolicited temperature and humidity reports arrive over time
   before considering recurring delivery verified. Keep the reading freshness
   setting greater than the configured maximum reporting interval.

SONOFF specifies Zigbee 3.0 operation, a CR2477 battery, temperature accuracy
of ±0.2°C, humidity accuracy of ±2% RH, and a shortest five-second report
interval after a value changes. It says the sensor reports at least once per
hour when values remain unchanged. These are manufacturer specifications, not
measurements from this gateway; device firmware and reporting configuration
can affect observed behavior. See the [product specifications](https://sonoff.tech/en-us/products/sonoff-zigbee-temperature-and-humidity-sensor-snzb-02p/58).

Battery percentage uses the standard half-percent representation when returned;
voltage is shown only when present. Battery reports and temperature/humidity
reports have separate timestamps and freshness. This implementation does not
write the SNZB-02P's vendor-specific calibration attributes or perform OTA.

## Hardware acceptance still required

When a physical unit is available, record its exact manufacturer/model/build,
endpoint and input/output clusters. Verify pairing, temperature, humidity,
battery percentage and voltage if advertised, signal metrics, reporting
configuration/readback, and unsolicited change/heartbeat reports without
repeated wake-ups. Also verify sensor rejoin and recurring reports after
gateway restart, and confirm missing battery attributes remain absent. Update
the dated validation record with observed evidence; do not infer a pass from
the simulator.

References: [SONOFF product page](https://sonoff.tech/en-us/products/sonoff-zigbee-temperature-and-humidity-sensor-snzb-02p/58), [SNZB-02P manual](https://support.sonoff.tech/snzb-02p-usermanual/), and [upstream SONOFF Zigbee converter profile](https://github.com/Koenkk/zigbee-herdsman-converters/blob/master/src/devices/sonoff.ts).
