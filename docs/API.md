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

The board accepts a single `after` query parameter containing decimal digits in
the range 0–4294967295. Invalid, repeated or additional event query parameters
return 400. Cursor arithmetic remains bounded at the maximum value; if the event
sequence exhausts uint32_t, the board changes `boot_id` and resets its ring to
start a new cursor epoch. A boot ID change therefore also signals a cursor epoch
change, even if uptime has not reset.

Command bodies must be JSON objects with no trailing data, literal/escaped NULs or
duplicate field names. Pairing health reflects permit-join status notifications
from the Zigbee stack as well as accepted API requests.

## SBC routes

GET `/api/v1/state`: `{gateway, devices, locations}` including endpoint maps, latest raw attributes, normalized values, receipt timestamps and location assignments. GET `/api/v1/events`: latest 100 raw events, including `received` and `boot_id`. POST `/api/v1/commands`: same command schema, with strict validation and upstream forwarding. Static dashboard paths are public but contain no telemetry or credentials.

GET `/api/v1/capabilities` describes SBC-supported operations, limits and feature
flags. It is available before the gateway connects. It does not promise that a
particular device supports an operation. Use `/api/v1/state` for connection and
readiness, and discovered input clusters to decide which device controls to show.
Configuration, layouts and queried history are implemented through the dashboard
v2 API and their capability flags are true. Command tracking and streaming remain false.
Named locations are implemented and advertised separately as `features.locations`.
`device_configuration` now covers v2 names, freshness windows and location
assignment. The v1 location APIs remain available and update the same revision.

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

The executable descriptions are in `sbc/contracts.py` and `sbc/contracts_v2.py`. After changing them, run
`python3 -m sbc.contracts` to regenerate the checked-in JSON documents, then
`python3 -m sbc.contracts --check`. The v1 contract version is 1.3.0; the separate
dashboard v2 contract is 2.0.0. Both remain available during migration.

Runtime needs only Python's standard library. Contract tests additionally use
`python3 -m pip install -r requirements-dev.txt`; then run
`python3 -m unittest discover -s tests -v`. Tests check real simulator/SBC payloads
with JSON Schema, schema validity and exported-contract consistency. Simulator
verification is not a firmware or hardware compatibility test.

Optional Chromium interaction tests use `requirements-browser.txt` and
`python3 -m playwright install chromium` (the host also needs Chromium's OS
libraries). Run `python3 -m unittest discover -s tests -p 'browser_*.py' -v`.
They cover tabs, locations, widget editing/ordering/ranges, multiple endpoints,
mobile width, edit conflicts, stale/invalid/offline readings and logout during
pending telemetry/history requests.

## Implemented dashboard v2 API

All routes use `DASHBOARD_TOKEN`; the browser continues to use v1 commands and
location CRUD. GET `/api/v2/openapi.json` publishes the
[dashboard v2 contract](api/dashboard-v2.openapi.json).

| Method / route | Result |
| --- | --- |
| GET `/api/v2/capabilities` | Implemented widget types, features and query/configuration limits |
| GET `/api/v2/gateway` | Existing gateway connection/readiness and ingestion status |
| GET `/api/v2/devices` | Named devices, assigned location, freshness and endpoint measurements |
| GET `/api/v2/configuration` | `schema_version`, `revision`, locations, device settings, dashboard layout; strong ETag |
| PUT `/api/v2/configuration` | Atomically replace editable locations/devices/dashboard with required `If-Match` |
| GET `/api/v2/history` | Filtered, paginated measurement history and known ingestion interruptions |

Configuration GET/PUT returns `ETag: "configuration-N"`. PUT accepts exactly
`locations`, `devices` and `dashboard`; missing revision returns 428, stale revision
412, invalid configuration 422 and a body over 64 KiB 413. Locations use existing
server-generated IDs; create them through v1. Limits are 50 locations, 50 device
settings and 100 widgets. Device settings support optional name, nullable location
and freshness 60–604800 seconds (default 3600). Dashboard settings are title,
`temperature_unit` (`celsius`/`fahrenheit`) and widgets. Each widget requires unique
ID, type (`numeric`/`chart`), title, source `(ieee, endpoint, cluster, attribute)`,
unique position 0–99 and `time_range` (3600, 21600, 86400, 604800 or 2592000).
Names/titles are visible single-line text of 1–80 characters. Sources must match
supported measurements on discovered/observed endpoints. Current supported
measurements are temperature, humidity and On/Off reported state. Widgets follow
their source device's location. Configuration exports contain no gateway secrets.

History requires `ieee`, `endpoint`, `cluster`, `attribute`, `from`, `to`, with
optional `limit` (1–500, default 100) and `cursor`. Times are UTC Unix seconds;
`from < to` and requests span at most 31 days. Results are ordered by receipt
time and database ID, with `items`, opaque `next_cursor`, `gaps` and
`gaps_truncated`. Cursors bind to the original identity/time filters and survive
SBC restarts; changed or tampered cursors return 400. Invalid ZCL values remain
null samples rather than zeroes. Known outages, gateway restarts and ring overruns
create interruption records when prior receipt/poll evidence is available.
At most 500 gap markers are returned; truncation is explicit so clients avoid
connecting readings across unknown gaps. Historical retention and background pruning are 60 days. Historical rows older than this can be reviewed and explicitly purged from the System dashboard.

The authenticated System API exposes `GET /api/v2/system` and
`GET /api/v2/system/database` for bounded host and SQLite summaries.
`POST /api/v2/system/database/check` runs an explicit `PRAGMA quick_check(1)`;
it is not part of polling. `GET /api/v2/system/purge-preview` creates a
five-minute in-memory preview; `POST /api/v2/system/purge` requires its
`preview_id` and deletes eligible history in one transaction. Eligible tables
are `events`, `measurements`, `signal_samples`, `ingestion_gaps`, and
`plug_discontinuities`. Device registry/latest projections, locations, profiles,
settings, and commissioning/display/plug jobs are preserved. API error responses
are bounded and do not include filesystem paths or database contents.

The browser drains at most 20 history pages (10,000 readings) per chart refresh
and asks for a shorter range when truncated. Charts refresh at most every 30 seconds
unless the latest measurement changes. Telemetry refreshes every three seconds,
backs off to ten seconds after failures and cancels pending requests on logout.
Display-unit conversion never rewrites stored Celsius readings. Missing, invalid
and stale measurements are distinct; gateway connectivity is shown separately.

V2 errors use `{"error":{"code":"...","message":"...","details":[]},"request_id":"..."}`.
V1 error envelopes and command acceptance semantics are unchanged. Device-specific
discovery completion and durable command tracking remain future capabilities.

### Reporting commissioning

`GET /api/v2/commissioning` returns durable `jobs` (at most one per known device),
desired policy, progress/results, sensor contact time, observed Basic identity,
and latest measurement receipt/origin. `POST /api/v2/commissioning` accepts:

```json
{"ieee":"a4c13804d148ffff","endpoint":1,"min_interval":5,"max_interval":3600,"temperature_change":0.2,"humidity_change":1,"model_hint":"SONOFF SNZB-02WD"}
```

The identity, endpoint, interval and `model_hint` fields are required. Supply
`temperature_change` when the endpoint exposes temperature and `humidity_change`
when it exposes humidity; omit thresholds for unsupported measurements. At least
one measurement is required. Existing dual-measurement requests remain valid.
`model_hint` may also be empty. Changes are in °C / RH
percentage points, exact hundredths; maximum must be 1–65534 seconds and at least
the minimum (0–65534). This bounded policy does not support ZCL disable/reset
intervals. A discovered active endpoint exposing temperature, humidity or both is
required. Temperature-only sensors generate no humidity commands. Returns 202 queued, 409 already active, 422 invalid input/endpoint, or
503 if gateway offline or firmware lacks `reporting_commissioning` in health.
POST `{"ieee":"a4c13804d148ffff","action":"cancel"}` returns 200 and stops future
attempts. Layout revisions are independent of this workflow. Existing v1 routes
and token authentication remain available. The generated v2 contract describes
job states; raw results include operation, status, phase and correlation ID.

Gateway `/api/v1/commands` adds `bind`, `configure_reporting`, `read_reporting`
and `reporting_window`, each requiring `ieee`, `endpoint` and a 36-character
hex/dash `request_id`. Sensor Bind accepts clusters 1, 6, 32, 1026 and 1029; reporting accepts temperature/humidity attribute 0 and supported Power Configuration battery attributes 32/33. Exact model/endpoint capabilities and the generated schemas govern each workflow. Configure also takes `min_interval`,
`max_interval`, `reportable_change` in raw hundredths (positive, at most 32767 for
temperature or 10000 for humidity). Window takes `seconds` 0–120. These commands
accept exactly their documented fields and always bind to local coordinator
IEEE/endpoint 10. 202 is local acceptance only. Correlated `commissioning` events
carry `response`, `transport_error` or `timeout` phase; remote status zero is
success only for a response. ZCL responses match source address, endpoint,
cluster and confirmed transaction sequence; expired attempts are discarded.
Readback carries attribute data type, intervals and raw delta when successful.
The gateway bounds outstanding operations to 16, one per source/cluster, with a
25-second deadline. Full end-to-end command tracking for other v1 operations is
still unavailable. Attribute events add `origin: report|read_response`; retained
older events are interpreted as `unknown`.

## SNZB-02UL advance support

See [SNZB-02UL preparation](SNZB_02UL.md) for profile defaults, battery scaling, display APIs, firmware upgrade requirements and pending physical checks. Generated contracts include the sensor-profile/display routes and bounded gateway operations.

## SNZB-02P sensor profile

The sensor-profiles response and `model_hint` enum include `SONOFF SNZB-02P`.
Commissioning uses the standard temperature/humidity reporting workflow and
may optionally bind the Power Configuration cluster and read battery attributes
when the model is observed. Battery voltage is included only if returned by the
device. See [SNZB-02P setup and verification](SNZB_02P.md); physical acceptance
remains pending.

## Session-based user profiles

The v2 API supports `GET/POST /api/v2/profiles` and `PUT/DELETE /api/v2/profiles/{profile_id}`. Configuration resolves `X-Dashboard-Profile` before the `dashboard_profile` session cookie and returns the resolved profile header plus a profile-scoped ETag. Admin remains the backward-compatible default. Profile IDs are presentation selectors, not credentials. See [profile semantics and errors](USER_PROFILES.md).

Signal history and latest RSSI are available through the authenticated v2 devices/history APIs; see [signal history](SIGNAL_HISTORY.md) for the dashboard-only source identifier and event correlation.

Per-profile All layout preferences are part of v2 configuration; see [All layout API and compatibility](ALL_LAYOUT.md).

Gateway health includes `gateway_id` and `network` recovery diagnostics; the optional authenticated bounded outage endpoint is documented in [Wi-Fi recovery](WIFI_RECOVERY.md). Discovery uses UDP 39128 with nonce/HMAC proofs; it never broadcasts bearer tokens.

S60ZBTPG smart-plug operation, observed hardware results and remaining hardware/OTA/timing acceptance: [S60ZBTPG.md](S60ZBTPG.md).


The implemented S60ZBTPG API is `GET /api/v2/plug-profiles` and `GET/POST /api/v2/plugs`; actions include read/commission/relay/startup_behavior/network_indicator/outlet_protection/protection/inching. Job acceptance, remote response and matching readback are distinct. `acknowledged_unverified` for inching is not a measured timing result. Capabilities marked `not_tested`/`prepared` in runtime metadata are conservative static declarations, not a live certification database; see the dated [hardware evidence](HARDWARE_VALIDATION_2026-10-18.md) for checks completed since the implementation was merged.

The React dashboard uses the existing API plus the additive `grid_layout` field in dashboard-v2 2.10.0; [layout contract and migration](DASHBOARD_MIGRATION.md) describe All and per-location screen geometry. No firmware API or device write protocol changed.

Version 2.10.0 adds optional bounded `grid_layout.presentation` settings for profile defaults and tile/widget typography/scale overrides. Older clients omitting the field preserve saved preferences. See the [presentation contract](DASHBOARD_APPEARANCE.md#stored-api-fields).
