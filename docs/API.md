# API contract, v1

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

GET `/api/v1/state`: `{gateway, devices}` including endpoint maps, latest raw attributes, normalized values and receipt timestamps. GET `/api/v1/events`: latest 100 raw events, including `received` and `boot_id`. POST `/api/v1/commands`: same command schema, with strict validation and upstream forwarding. Static dashboard paths are public but contain no telemetry or credentials.

```bash
curl -H "Authorization: Bearer $GATEWAY_TOKEN" "$GATEWAY_URL/api/v1/health"
curl -H "Authorization: Bearer $GATEWAY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"op":"permit_join","seconds":60}' "$GATEWAY_URL/api/v1/commands"
```

Tokens do not travel in URL query strings. Commands have no durable IDs, correlation, idempotency guarantee or confirmation promise. A timed-out HTTP command may have executed; check device state before a manual retry.
