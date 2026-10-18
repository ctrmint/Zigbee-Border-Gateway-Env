# Zigbee Border Gateway Env

A local home automation starter for **20–50 devices**, using the Espressif **ESP Thread Border Router / Zigbee Gateway board (ESP32-S3 + ESP32-H2)** and a Linux SBC.

The board runs Zigbee coordinator firmware, exposes an authenticated local REST API and communicates with the H2 radio over its onboard UART. The SBC hosts a dashboard, API proxy and SQLite device/history store. Your own dashboard can call the board API directly from its backend, or use the SBC API.

**Status: development system with recorded hardware validation.** Three SONOFF temperature sensors and three S60ZBTPG plugs have been connected. Plug identity, reporting/readback, physical-button and remote switching on one unit, live electrical telemetry and selected settings have hardware evidence. See the [18 October hardware record](docs/HARDWARE_VALIDATION_2026-10-18.md) for exactly what was tested and [validation](docs/VALIDATION.md) for automated checks and outstanding acceptance. A 50-device network has not been load tested. This is not a Zigbee2MQTT replacement or a universal commercial-device compatibility layer.

## Included

- S3 firmware: coordinator formation and persistence, explicit 0–180 second pairing, 50-entry IEEE-address registry, automatic endpoint/cluster discovery on announcement, standard scalar attribute reports and reads, On/Off commands, bounded event history.
- H2 RCP build recipe using ESP-IDF's supplied `ot_rcp` source.
- SBC Python service with SQLite history, restart-aware polling, deduplication, gap detection and authenticated command proxy.
- Tabbed dashboard: read-only All overview, location tabs and Configuration & Setup, configurable numeric readings/history charts, pairing, inventory and endpoint inspection. Presentation profiles have session-cookie selection and independent layouts; device state/settings remain shared.
- Bounded sensor reporting/display and S60ZBTPG plug jobs with acknowledgements/readback, metering/state/RSSI history and model-specific controls.
- Continuous gateway Wi-Fi recovery and authenticated identity-pinned rediscovery; retained event ages and recording gaps remain visible.
- Named locations: create/rename locations, assign multiple sensors and group readings; saved on the SBC across restarts.
- Saved device names, freshness windows, widget titles/order and chart ranges; revision checks protect edits between browser sessions. Indexed measurement history migrates existing events and marks known ingestion interruptions.
- Explicit simulator with two sample devices; usable without hardware.
- Hardware BOM, architecture, flashing, API, security, operations and compatibility documentation.

## Try it without hardware

Requires Python 3.11 or newer. No Python packages need installing.

```bash
cd zigbee-border-gateway
cp .env.example .env
# Edit .env: set TWO different random tokens, each at least 32 characters.
# Generate each with: python3 -c 'import secrets; print(secrets.token_hex(32))'
set -a
. ./.env
set +a
python3 -m sbc.simulator
```

In a second terminal, load the same `.env` then run:

```bash
python3 -m sbc.app
```

Open <http://127.0.0.1:8080>, paste `DASHBOARD_TOKEN`, then Connect. The dashboard clearly labels simulated data. Use separate `DB_PATH` values for demo and real deployments to avoid mixing histories.

## Build the physical solution

1. Select the S3/H2 board in [HARDWARE_BOM.md](HARDWARE_BOM.md).
2. Follow [firmware setup](docs/FIRMWARE_SETUP.md), flashing H2 first and S3 second.
3. Set `GATEWAY_URL` to the board's DHCP-reserved IP and `GATEWAY_TOKEN` to the configured firmware token. Set `DB_PATH=data/hardware.sqlite3`.
4. Start the SBC service and open pairing for one device at a time. Wake sleepy devices during discovery.
5. Inspect endpoints before controlling devices. Read attributes to verify reports and state.

For another machine to access the dashboard, set `BIND_HOST=0.0.0.0` only on a trusted LAN, firewall its port, or keep localhost and use an SSH tunnel. For ongoing use, see [SBC deployment](docs/SBC_SETUP.md).

## Repository

| Path | Purpose |
| --- | --- |
| `firmware/` | ESP-IDF S3 application and components |
| `firmware/rcp/` | H2 configuration and build instructions |
| `sbc/` | Python API, poller, database and dashboard assets |
| `tests/` | Network-backed simulator/SBC integration tests |
| `docs/` | Setup, protocol, operations, limitations and validation |
| `scripts/` | Demo launch and archive helper |
| `requirements-dev.txt` | Dependencies for local software validation |

## Validate and publish

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q sbc tests
```

Install contract-test dependencies first with
`python3 -m pip install -r requirements-dev.txt` (prefer a virtual environment).
The service and simulator themselves still require no third-party packages.
Run `python3 -m sbc.contracts --check` to verify the exported API descriptions.
See the [API contracts](docs/API.md) and
[configurable dashboard development plan](docs/DASHBOARD_API_DESIGN.md).

This repository is maintained on GitHub. Work on a branch, validate the change, and merge through a reviewed pull request. Keep hardware acceptance evidence separate from simulator results and update the relevant product guide and issue when new physical checks are completed.

Do not commit `.env`, generated `sdkconfig`, build artifacts or network/database backups. Original project code is MIT; Espressif example-derived files retain their notices. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Current limits

User-initiated binding/report configuration and selected SONOFF adapters are implemented. Pairing alone does not configure reporting; use the appropriate Setup workflow and inspect its remote responses/readback. General-purpose device adapters, IAS Zone enrolment, OTA, MQTT, automation rules and secure Zigbee-network backup/restore remain outstanding. Plug OTA is tracked in #30; schedules/countdowns/scenes and inching timing verification in #31. See [device compatibility](docs/DEVICE_COMPATIBILITY.md).

See [SNZB-02UL preparation](docs/SNZB_02UL.md) for the advance sensor-support milestone and pending hardware validation.

The read-only [All sensors overview](docs/DASHBOARD_ALL.md) displays compact sensor tiles across every location, with responsive tablet layouts.

[User profiles](docs/USER_PROFILES.md) provide session-cookie selection and separate dashboard preferences/layouts without individual logins.

[Sensor signal strength and history](docs/SIGNAL_HISTORY.md) describes passive RSSI logging and dashboard widgets.

[All dashboard layout settings](docs/ALL_LAYOUT.md) provide per-profile columns, minimum tile widths and sensor ordering.

[Continuous Wi-Fi recovery](docs/WIFI_RECOVERY.md) covers autonomous reconnection, authenticated rediscovery and outage validation.

S60ZBTPG smart-plug operation, observed hardware results and remaining acceptance: [docs/S60ZBTPG.md](docs/S60ZBTPG.md).
