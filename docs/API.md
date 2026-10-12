# API contract, v1

The browser talks to the SBC on this host. The SBC talks to the ESP32 coordinator.
These are separate contracts with different data ownership and credentials.

Machine-readable [OpenAPI 3.1](https://spec.openapis.org/oas/v3.1.0.html) documents:

- [Dashboard/SBC API](api/dashboard-v1.openapi.json)
- [ESP32 gateway API](api/gateway-v1.openapi.json)

The SBC also serves its contract at authenticated GET `/api/v1/openapi.json` and
feature discovery at GET `/api/v1/capabilities`. These describe implemented
features; the [dashboard development plan](DASHBOARD_API_DESIGN.md) defines proposed
configuration, device, history and command resources separately.

All gateway API routes require `Authorization: Bearer <GATEWAY_TOKEN>`. SBC API routes require a **different** `DASHBOARD_TOKEN`. The firmware serves HTTP on port 80. SBC defaults to localhost:8080. Board CORS is deliberately absent; use your dashboard's backend/SBC proxy for browser access.

| Method / board route | Result |
| --- | --- |
| GET `/api/v1/health` | `boot_id`, `ready`, `mode`, `join_seconds`, `latest_seq`, `uptime_ms`, `dropped_events` |
| GET `/api/v1/devices` | `boot_id`, `devices`: IEEE/NWK/active registry |
| GET `/api/v1/events?after=0` | Up to 16 events, `boot_id`, `gap`, `next_seq`, `latest_seq` |
| POST `/api/v1/commands` | 202 and `accepted:true` on stack acceptance; 400 invalid input/device; 503 not ready/busy/rejected |

IEEE addresses are 16 hexadecimal digits without separators. Endpoints are 1–240; cluster/attribute identifiers are JSON integers, not hexadecimal strings.

```json
{"op":"permit_join","seconds":60}
```
```json
{"op":"permit_join","seconds":0}
```
```json
{"op":"discover","ieee":"00124b0000000001"}
```
```json
{"op":"on_off","ieee":"00124b0000000001","endpoint":1,"state":false}
```
```json
{"op":"read","ieee":"00124b0000000002","endpoint":1,"cluster":1026,"attribute":0}
```

Basic manufacturer/model reads use cluster 0 and attribute 4/5. Destination devices must already be in the board registry. Sleepy devices may not answer until awake. The application does not validate whether a remote endpoint supports a requested cluster; inspect discovery results first.

## Events

Types: `network_ready`, `announce`, `leave`, `discovery`, `endpoint`, `attribute`, `zcl_response`, `registry_full`. All carry a sequence and gateway uptime. Device events contain `nwk`, and `ieee` when a registry match exists. Unknown-address reports are retained as raw events but cannot update an identified device until discovery/rejoin.

```json
{"type":"attribute","seq":12,"uptime_ms":19000,"nwk":9029,"ieee":"00124b0000000002","endpoint":1,"cluster":1026,"attribute":0,"data_type":41,"raw":2050,"rssi":-50}
```

Ring capacity is 64 events, 768 bytes per serialized event. Oversized events increment `dropped_events`. `gap` covers cursor overruns/restarts; it does not describe every possible radio loss. Drain using `next_seq`, not `latest_seq`; poll again immediately when they differ. Compare boot IDs before updating cursors.

## SBC routes

GET `/api/v1/state`: `{gateway, devices, locations}` including endpoint maps, latest raw attributes, normalized values, receipt timestamps and location assignments. GET `/api/v1/events`: latest 100 raw events, including `received` and `boot_id`. POST `/api/v1/commands`: same command schema, with strict validation and upstream forwarding. Static dashboard paths are public but contain no telemetry or credentials.

GET `/api/v1/capabilities` describes SBC-supported operations, limits and feature
flags. It is available before the gateway connects. It does not promise that a
particular device supports an operation. Use `/api/v1/state` for connection and
readiness, and discovered input clusters to decide which device controls to show.
Configuration, layouts, queried history, command tracking and streaming flags
currently remain false.
Named locations are implemented and advertised separately as `features.locations`.
`device_configuration` refers to the future full device-settings document,
not the implemented location assignment.

GET `/api/v1/openapi.json` returns the dashboard contract. Both new routes require
`DASHBOARD_TOKEN`, return JSON with `Cache-Control: no-store`, and never expose the
gateway token or host configuration. Existing response fields remain compatible.

Before the first successful poll, `gateway` contains only `connected`, `error`
and `gap`; network fields are optional. `last_poll` is the SBC's last successful
poll time. Previously received measurements remain available during outages.
`last_seen` and attribute `received` are SBC receipt times, not RF observation
timestamps. `endpoints` is keyed by decimal endpoint strings, and `attributes`
by `endpoint:cluster:attribute`. Raw history is not normalized; latest attribute
projections include `value`, `unit` and `received`.

SBC validation errors are JSON `{"error":"message"}`. Firmware HTTP errors may
be non-JSON; parse the status before assuming a response body shape. The SBC
currently translates upstream HTTP errors/timeouts to 502 rather than preserving
the board's status. A 502 command response therefore has an uncertain execution
outcome. Commands are limited to 512 bytes on both services.

Response objects allow additive fields. Request objects reject extra fields on
the SBC; firmware v1 currently ignores them. Use the stricter dashboard schema
for all clients. The OpenAPI gateway contract describes those existing firmware
semantics; exporting it does not add routes or version negotiation to the board.

```bash
curl -H "Authorization: Bearer $GATEWAY_TOKEN" "$GATEWAY_URL/api/v1/health"
curl -H "Authorization: Bearer $GATEWAY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"op":"permit_join","seconds":60}' "$GATEWAY_URL/api/v1/commands"
```

Tokens do not travel in URL query strings. Commands have no durable IDs, correlation, idempotency guarantee or confirmation promise. A timed-out HTTP command may have executed; check device state before a manual retry.

## Named locations on the SBC

Locations are application metadata, stored separately from the ESP32 registry.
One location can contain multiple devices; a device has one location or is
unassigned. Names are dynamic and can describe rooms, buildings or outdoor areas.
Stable server-generated UUIDs preserve assignments when a location is renamed.

| Method and SBC route | Body / result |
| --- | --- |
| GET `/api/v1/locations` | `{locations:[{id,name,device_count}]}` |
| POST `/api/v1/locations` | `{name}` → 201 `{id,name,device_count}` |
| PUT `/api/v1/locations/{id}` | `{name}` → 200 renamed location |
| DELETE `/api/v1/locations/{id}` | 200 `{deleted:true}`; 409 while assigned |
| PUT `/api/v1/devices/{ieee}/location` | `{location_id:UUID}` or `{location_id:null}` → 200 `{ieee,location_id}` |

All routes use `DASHBOARD_TOKEN`; no gateway connection is required. Unknown
devices/locations return 404. Malformed input returns 400; duplicate names or
the 50-location limit return 409. Names are 1–80 characters, trimmed and Unicode
normalized, with no controls or line breaks. Names are unique after Unicode
normalization and case folding. Mutating bodies are at most 512 UTF-8 bytes and
reject extra fields. Updates use last-write-wins in v1; revision-based full
configuration editing remains a v2 proposal.

`/api/v1/state` includes `locations` and nullable `location_id`/`location_name`
on each device, read together under the store lock. Device counts include
departed devices whose assignments are retained. The browser displays devices
under their location names, with an Unassigned group. Location names are plain
text and never rendered as HTML.

New tables are created automatically when opening an existing SBC database.
Pairing, polling, device departure and short-address changes preserve location
assignments. Database backups now include location configuration. Move or
unassign devices before deleting a location; deletion never silently removes
assignments. There are no changes to the ESP32 API.

## Maintaining the contracts

The executable descriptions are in `sbc/contracts.py`. After changing them, run
`python3 -m sbc.contracts` to regenerate the checked-in JSON documents, then
`python3 -m sbc.contracts --check`. The contract version is 1.2.0; route version
remains v1 because these changes are additive.

Runtime needs only Python's standard library. Contract tests additionally use
`python3 -m pip install -r requirements-dev.txt`; then run
`python3 -m unittest discover -s tests -v`. Tests check real simulator/SBC payloads
with JSON Schema, schema validity and exported-contract consistency. Simulator
verification is not a firmware or hardware compatibility test.

Optional Chromium interaction tests use `requirements-browser.txt` and
`python3 -m playwright install chromium` (the host also needs Chromium's OS
libraries). Run `python3 -m unittest discover -s tests -p browser_locations.py -v`.
They cover naming, multi-device assignments, renaming, unassignment/deletion,
mobile width and logout during a pending refresh.
