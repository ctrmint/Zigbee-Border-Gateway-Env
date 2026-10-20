# Radio dashboard

The **Radio** tab sits beside **System** and provides a read-only view of the Zigbee coordinator's local mesh information and recorded signal history. It follows the existing Mantine dashboard cards and tables, refreshes every 30 seconds, and offers a manual refresh. Selecting a device only changes the displayed history query; the dashboard sends no Zigbee command, attribute read, topology request, or sleepy-device wake-up.

## Metrics and scope

The S3 gateway exposes a bounded snapshot through authenticated `GET /api/v1/radio`. It reads the coordinator's current neighbor table, routing table and source-route table while holding the Zigbee stack lock. Each table is limited to 64 entries. The dashboard reports the snapshot source and age, coordinator readiness, channel, PAN ID, local direct-neighbor LQI/RSSI, link relationship/depth/age, route destination/next hop/state and source-route paths. The gateway's event-drop and event-sequence counters are included.

Neighbor entries describe links known by the coordinator. They do not expose each router's own neighbor table and cannot be presented as a complete topology. RSSI is reception strength of messages received by the coordinator; it is not used to infer a route or signal quality elsewhere in the mesh. Route expiry counters are omitted because the pinned SDK does not document their unit. Table entries are instantaneous snapshots; trend history for LQI and route changes is not yet recorded.

The Radio page also plots up to 500 passive per-device coordinator RSSI samples from the last 24 hours, using the existing `/api/v2/history` signal source. The history remains under the existing 60-day retention policy. It is bounded and does not generate extra radio traffic.

The current gateway does not expose MAC retry/delivery-failure counters, channel utilization, noise floor or interference measurements. The page marks these as unavailable rather than estimating them. Future collection should remain bounded and passive unless a separately designed, explicit diagnostic operation is justified.

## API and compatibility

The SBC poller caches one local-table snapshot for up to 30 seconds and serves it through authenticated `GET /api/v2/radio`. An older gateway returning 404 is reported as unsupported; transient failures retain a prior snapshot marked stale. Poll failures do not interrupt normal measurement ingestion. The v1 gateway and v2 dashboard OpenAPI files describe the new APIs.

The simulator serves clearly labeled synthetic neighbors for UI and API testing. Simulated values are not hardware evidence. Existing configuration, profile preferences, readings and history schemas are unchanged.

## Validation boundary

Automated checks can verify schema validation, bounded snapshots, simulator labels, stale/unsupported handling and responsive rendering. A firmware build verifies compilation against the pinned ESP-Zigbee SDK. Only a physical gateway can verify that populated neighbor/route tables match the live network and that the stack iterator APIs behave as expected on the deployed board. No such radio-table hardware observation is implied by a simulator run.
