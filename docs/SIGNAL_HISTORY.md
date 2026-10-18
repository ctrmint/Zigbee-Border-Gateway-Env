# Sensor signal strength (#23)

Setup cards, location pages and the read-only All overview display the latest received RSSI in dBm and its age. More negative values mean weaker signal at the coordinator. RSSI describes reception of a particular message, not battery condition, a guaranteed current connection, or proof of why another message was lost. No qualitative strength thresholds are applied.

Choose **Add widget → Device endpoint measurement → Signal strength**, then a numeric reading or history chart, to add signal widgets to a location. Widgets use the selected user's saved layout. Automatic signal summaries need no layout changes. All stays read-only and never requests history or radio operations.

## Recording, retention and API

Every incoming event with a sensor identity and valid signed integer RSSI (-128 through 126 dBm) is stored; 127 is treated as unavailable. Missing, non-integer and out-of-range values do not replace the last valid observation. No LQI-to-RSSI conversion or fabricated signal values are used. Events without RSSI can still update other telemetry normally. Logging never wakes devices, issues reads or changes reporting settings.

SQLite `signal_samples` retains 30 days of data, pruned on startup and the existing periodic maintenance cycle. `signal_latest` retains each device's last valid observation independently, even after history expiry, so the dashboard can show its value, timestamp and stale state. Freshness uses that device's saved freshness window, independently of temperature/humidity timestamps. An unknown sensor signal is shown as **Signal: not received**. An unavailable gateway remains a separate connectivity state.

First startup backfills valid RSSI from retained raw events using their original Pi reception timestamps. Backfill does not recreate pruned events, and it does not rerun after normal restarts. Existing device settings, locations, policies and profile layouts are unchanged. The available history starts at the earliest retained RSSI-bearing event; it is not a promise of measurements before recording began. Firmware need not change: the current gateway already supplies RSSI with attribute events.

Authenticated `GET /api/v2/devices` adds `signal` to each device: value/unit/received_at/quality, freshness, original gateway boot/sequence and original event metadata where observed. These values remain separate from measured temperature/humidity and battery.

Signal widgets reuse `GET /api/v2/history` with the dashboard-only source `endpoint=1&cluster=65535&attribute=0`, plus the normal `ieee`, `from`, `to`, `limit` and optional signed `cursor`. Endpoint 1 here is a logical device-wide source, not an assertion about the endpoint that received the message. This reserved source must never be sent over Zigbee. History has the existing 31-day query range, 500-item page limit and 10,000-point chart bound. Signal samples include `boot_id`, `seq`, `source_endpoint`, `source_cluster`, `source_attribute`, `event_type` and `origin`; absent original metadata remains null. `(boot_id, seq)` links a signal sample to its raw event and measurement. Measurement history now also returns `boot_id`, `seq` and the corresponding `rssi` when retained. Gateway sequence restarts do not collide across boots.

## Deployment and rollback

Stop the Pi dashboard service, take a consistent SQLite backup and preserve the current source, then restart with this source. Migration is local to the Pi. No gateway flash, network reset, re-pairing or sensor command is needed. Preserve newly collected history before any rollback. Restore matching source and database together with the service stopped; older versions cannot render saved signal widgets. Credentials, backups and hardware data stay private and Git-ignored.

The user confirmed physical iPad acceptance and [#23](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/23) is closed. Device/version and detailed chart interactions were not supplied; no additional results are inferred. Automated WebKit emulation remains a separate validation record. Signal reporting also applies to metering plugs, but RSSI alone does not establish a sensor’s mesh route.
