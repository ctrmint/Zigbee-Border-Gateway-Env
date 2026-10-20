# System dashboard (#43)

The System utility tab sits beside Configuration & Setup. It is authenticated
with the normal dashboard bearer token, is not selected by default, and is
read-only except for its explicit historical purge action. It does not issue
Zigbee commands or wake sleepy sensors.

Host values are sampled from standard Linux `/proc`, `/sys`, platform metadata,
and filesystem APIs without invoking a shell or requiring root. Unsupported
values are shown as unavailable. Host sampling is cached for 15 seconds and the
browser refreshes it every 30 seconds. The process restart count and systemd
service state are not exposed because the dashboard process has no privileged
service-manager integration. CPU utilization is unavailable until two samples
have been collected. Network addresses are limited to interface IPv4 addresses.

The database section reports database/WAL/journal file sizes, page and free-page
counts, selected table row counts, oldest/newest retained timestamps, and latest
ingestion time. SQLite `quick_check(1)` runs only after the operator requests it.
It does not run on each dashboard refresh.

All telemetry history is retained for 60 days and background pruning uses the
same window. The purge flow first creates an authenticated preview token that
expires after five minutes, then presents the exact cutoff and row counts for
explicit confirmation. One transaction deletes only older rows from:

- `events` by `received`
- `measurements` by `received`
- `signal_samples` by `received`
- `ingestion_gaps` by `end`
- `plug_discontinuities` by `received`

The purge preserves devices and latest attribute projections, locations,
profiles, assignments, dashboard preferences, device settings, and operational
commissioning/display/plug job records. It does not run `VACUUM`; SQLite may keep
freed pages available for reuse, so the reported database file size may not
shrink immediately. A database transaction failure rolls back the purge.

Upgrades cannot restore history already removed under the former 30-day
retention policy. The APIs are `GET /api/v2/system`,
`GET /api/v2/system/database`, `POST /api/v2/system/database/check`,
`GET /api/v2/system/purge-preview`, and `POST /api/v2/system/purge`.
