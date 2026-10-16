# SNZB-02UL preparation (#14)

SONOFF AirGuard SNZB-02UL support was prepared before connection and first paired on 16 October 2026. Core reporting is now verified on one physical unit; display settings and sustained/restart behavior remain pending. Selecting a profile never fabricates a paired registry entry.

Protocol reference: [SONOFF product](https://sonoff.tech/products/sonoff-airguard-series-e-ink-zigbee-temperature-humidity-sensor-snzb-02ul) and [upstream converter, pinned revision 3956a2c75e37e467ca5cb9e537923317fdbe80de](https://github.com/Koenkk/zigbee-herdsman-converters/blob/3956a2c75e37e467ca5cb9e537923317fdbe80de/src/devices/sonoff.ts). Runtime code is local Python/C; the upstream converter is evidence, not a runtime dependency.

| Capability | Software status | Physical status |
| --- | --- | --- |
| Basic identity, descriptors, temperature/humidity | Implemented | SONOFF / SNZB-02UL, build 1.0.3; unsolicited reports observed |
| Reporting defaults, binding and readback | Implemented | All 10 setup steps verified; actual saved policy 5/3600 s, 0.2°C / 1% RH |
| Battery percentage; voltage if observed | Implemented | Read 100% and 3.2 V; reporting configuration/readback verified |
| Display units, comfort thresholds, calibration targets | Validated scalar write/readback implementation | Pending |
| Coordinator Time service | Implemented, synchronized lease | Sensor consumption pending |
| Remote sensor payload and weather reply | Tested codecs only; transport disabled | Deferred [#16](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/16) |
| OTA | Disabled | Deferred [#17](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/17) |

## Reporting and measurements

New UL policies default to minimum 5 seconds, maximum 1800 seconds, temperature change 0.2°C and humidity change 1 percentage point. Recommended freshness is 2250 seconds. Existing model policies and saved freshness settings are preserved. Five seconds is not a guaranteed reporting cadence.

Commissioning binds to coordinator endpoint 10, verifies temperature/humidity reporting readback, and separately records optional On/Off and battery setup failures. On/Off binding is protocol setup: recognized sensor endpoints do not receive appliance controls. Basic manufacturer/model/software-build strings are retained separately from the user model hint. Descriptor capabilities determine available operations.

Battery percentage uses raw half-percent units (0–200), voltage uses tenths of a volt (0–254); 255 means unknown. Voltage is exposed only when observed. Battery has independent timestamps and a 48-hour freshness threshold; low battery means at most 20%. Contact, gateway connectivity, temperature freshness, battery freshness and commissioning state are separate. Local history contains actual measurements, never display settings or remote/weather payloads.

## Display settings and Time

Authenticated `GET /api/v2/sensor-profiles` describes readiness; `GET /api/v2/display` returns durable jobs. `POST /api/v2/display` accepts `ieee`, `endpoint` and `settings`, or an explicit cancel action. For example settings can contain `temperature_units: "celsius"` or `"fahrenheit"`. Comfort temperature limits are 0–50°C; humidity limits 5–95%; calibration targets are -50–50. Numeric inputs use 0.1 precision. Calibration is presented as a target, without claiming offset semantics.

Only whitelisted scalar attributes on a discovered vendor cluster 0xFC11 are writable. Each write requires correlated successful readback of the expected type/value. Jobs survive Pi restarts, retry with bounded delays, expire after five minutes and show partial writes or remote rejection. Cancellation cannot retract an already transmitted write. Verified means the last successful readback, not continuous observation of the display. Unsupported vendor capabilities remain visible diagnostics.

The Pi refreshes the coordinator clock every five minutes and after coordinator reboot when a registered UL needs it. The Time server uses the Zigbee epoch (2000-01-01), current local UTC offset and a 15-minute synchronization lease. Expired/unsynchronized time is invalid. It does not claim future DST transition rules; offset changes propagate on refresh. A valid coordinator clock does not prove the sensor requested or displayed it.

Remote/weather codecs have golden payload tests, but no remote-source selection, provider requests, coordinates, weather transmission or invented weather are enabled. Their remaining transport and UI work is explicitly tracked in #16.

## Upgrade and first pairing

Manufacturer pairing reference: [SONOFF SNZB-02UL English manual](https://cdn.shopify.com/s/files/1/0742/9963/8001/files/User_Manual_SNZB-02UL_EN.pdf), checked 16 October 2026. On first use, removing the battery insulation starts a three-minute pairing window. To enter it again, hold the sensor button for 5 seconds until the signal icon flashes slowly. A 10-second hold performs a factory reset, so release at the pairing indication. Open the Pi dashboard's **Pair for 60 seconds** window immediately before starting sensor pairing; reopen it if the gateway's shorter window expires. These instructions apply to the new UL, without resetting existing sensors.


1. Back up the Pi database, source and current private firmware/configuration. Preserve Wi-Fi/API credentials and Zigbee network storage. Never erase flash or reset the network for this upgrade.
2. Build and flash the S3 image using the established [firmware procedure](FIRMWARE_SETUP.md). H2 firmware does not change. Confirm gateway health advertises `sensor_extensions`. Older firmware remains usable for existing sensors; new UL setup/display operations are gated until upgraded.
3. Open a bounded permit-join window when the UL arrives. Record actual Basic identity, software build, descriptors and battery attributes; the simulator descriptor is synthetic.
4. Assign its endpoint to a location, choose the UL profile and queue commissioning while the device is awake. Inspect core readback and optional warnings separately. Unsupported optional features must not block core sensing.
5. Observe unsolicited change reports and at least two maximum intervals (one hour at the default). Manual reads are not evidence of automatic reporting. Verify units, battery, charts, display settings and Time behavior against the actual unit.
6. Restart Pi/coordinator and verify existing WD/LD devices and the UL continue reporting without re-pairing. Record each hardware result in #14.

On this Pi, the S3 application upgrade was installed on 16 October 2026. Live health now advertises `sensor_extensions`, the saved network and two existing device registrations were retained, and an explicit Pi clock-sync command produced a valid Time-service lease. The lease can expire while no UL is present; normal automatic refresh starts once an UL is identified/configured. Physical UL consumption of Time and all sensor-specific RF behavior remain pending. Other installations must install the prepared S3 firmware before UL commissioning. Roll back Pi source and its matching database backup together with the service stopped; retain a copy of any newer history first. Firmware rollback uses the saved image/configuration without erasing network storage. Completed display writes are device-side state and are not undone by restoring a Pi database.

## First physical validation, 16 October 2026

The paired unit identifies itself as SONOFF / SNZB-02UL, software build 1.0.3, endpoint 1, profile 0x0104, device 0x0302. Its input clusters are 0x0000, 0x0001, 0x0003, 0x0402, 0x0405, 0x0020, 0xFC57 and 0xFC11; output clusters are 0x000A and 0x0019. It does not advertise the optional On/Off input cluster, so no such binding was attempted.

All ten applicable commissioning steps completed with successful responses and matching readback, including battery reporting. The actual user-saved policy is 5/3600 seconds rather than the offered 5/1800-second reference default; it was preserved. Multiple genuine unsolicited temperature and humidity reports arrived after setup. Battery percentage and voltage were read from the device, not inferred. Two full maximum intervals, post-restart reporting, stale/offline behavior, E-Ink settings and sensor consumption of Time remain unverified. No display settings job has been submitted; the dashboard hardware-verification label refers specifically to those controls. Existing Garage and Fish Tank setup rechecks remain failed and require separate follow-up; this successful UL setup does not establish their post-upgrade reporting.
