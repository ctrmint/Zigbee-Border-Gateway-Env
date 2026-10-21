# Zigbee Border Gateway Env

A local-first Zigbee monitoring and control system built around Espressif's
ESP32-S3/ESP32-H2 gateway board and a Linux single-board computer such as a
Raspberry Pi. The ESP32-S3 runs the Zigbee coordinator and local API; the Pi
stores device data in SQLite and serves the dashboard. The Pi can also be used
as the ESP-IDF development workstation for building and flashing the board.

The board is marketed as an ESP Thread Border Router, but this project uses it
as a **Zigbee coordinator**. It does not form or route a Thread network.

## What it includes

- A Zigbee gateway API for pairing, device discovery, attribute reads and
  reports, and supported On/Off commands.
- A Python service that collects gateway data, records measurement history,
  tracks gaps and stale readings, and exposes an authenticated local API.
- A responsive dashboard with **All**, location, **Configuration & Setup**,
  **System**, **Radio**, and **Starlink** tabs. It includes sensor charts,
  gateway and database health, coordinator mesh diagnostics, and optional
  read-only Starlink router and dish monitoring.
- Model-specific setup for selected SONOFF sensors and S60ZBTPG smart plugs.
  See [device compatibility](docs/DEVICE_COMPATIBILITY.md) for tested scope and
  remaining hardware checks.
- A simulator for trying the dashboard and API without the ESP hardware.

Dashboard profiles only separate presentation preferences between browser
sessions. They are not user accounts or a security boundary. The dashboard
access token protects the API.

## Project status

This is a development-stage home project with recorded validation on selected
physical devices. SONOFF SNZB-02WD and SNZB-02LD sensors and S60ZBTPG plugs have
been exercised on hardware. SNZB-02UL and SNZB-02P software support is prepared,
with model-specific physical acceptance still pending. Starlink monitoring has
returned live router data and partial dish telemetry; dish fields vary by
terminal firmware. A 50-device
network has not been load-tested. This is not a universal Zigbee device layer
or a Zigbee2MQTT replacement. See the [validation record](docs/VALIDATION.md)
and [dated hardware evidence](docs/HARDWARE_VALIDATION_2026-10-18.md) for the
limits of each check.

## Try the simulator

Requires Python 3.11 or newer.

```sh
git clone https://github.com/ctrmint/Zigbee-Border-Gateway-Env.git
cd Zigbee-Border-Gateway-Env
cp .env.example .env
```

Edit `.env` and set separate random values for `GATEWAY_TOKEN` and
`DASHBOARD_TOKEN` (at least 32 characters each). Then start the simulator:

```sh
set -a
. ./.env
set +a
python3 -m sbc.simulator
```

In a second terminal, load the same `.env` and start the dashboard service:

```sh
set -a
. ./.env
set +a
python3 -m sbc.app
```

Open <http://127.0.0.1:8080> and connect with `DASHBOARD_TOKEN`. Simulated
readings are labelled in the dashboard. Keep simulator and real-device
databases separate by setting different `DB_PATH` values.

## Build and operate the hardware

Start with the [hardware bill of materials](HARDWARE_BOM.md), then follow the
[ESP firmware setup](docs/FIRMWARE_SETUP.md) and [SBC service setup](docs/SBC_SETUP.md).
The [operations guide](docs/OPERATIONS.md) covers service health, backups,
troubleshooting and recovery. Do not erase the Zigbee network as part of a
routine firmware update.

Starlink monitoring is optional and disabled until configured. Install the
optional gRPC runtime, then configure router and dish targets independently in
**Configuration & Setup → Starlink**. Dish status fields can be absent even
when the terminal is reachable; see the [Starlink monitoring guide](docs/STARLINK_MONITORING.md).

For direct LAN access, bind the service only to a trusted network and restrict
its port with a firewall. For occasional remote access, use an SSH tunnel.
Profiles do not replace access control, and the dashboard should not be exposed
directly to the public internet. See [security and privacy](SECURITY.md).

## Documentation

| Guide | Contents |
| --- | --- |
| [Device compatibility](docs/DEVICE_COMPATIBILITY.md) | Supported models, setup workflows and known device limits |
| [SONOFF SNZB-02P](docs/SNZB_02P.md) | Sensor setup, reporting behavior and pending hardware checks |
| [System dashboard](docs/SYSTEM_DASHBOARD.md) | Pi health, database status, retention and history purge |
| [Radio dashboard](docs/RADIO_DASHBOARD.md) | Coordinator mesh tables and passive signal history |
| [Starlink monitoring](docs/STARLINK_MONITORING.md) | Router and dish setup, collected fields and firmware limits |
| [Dashboard operation](docs/SBC_SETUP.md) | Locations, widgets, profiles and service configuration |
| [API contracts](docs/API.md) | Authenticated SBC and gateway API references |
| [Validation record](docs/VALIDATION.md) | Automated checks and dated hardware evidence |
| [Public project wiki](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/wiki) | Product overview, build, installation and operation |

## Development checks

Install the development dependencies in a virtual environment, then run:

```sh
python3 -m pip install -r requirements-dev.txt
python3 -m unittest discover -s tests -v
python3 -m compileall -q sbc tests
python3 -m sbc.contracts --check
```

The React dashboard source is in `frontend/`; Node.js is needed only to run its
tests or rebuild the committed production assets. See
[dashboard migration](docs/DASHBOARD_MIGRATION.md) for frontend build commands.

## License and third-party notices

Project code is MIT-licensed. ESP-IDF example-derived files retain their
upstream notices, and the Zigbee stack includes Espressif proprietary
prebuilt libraries. See [third-party notices](THIRD_PARTY_NOTICES.md) before
redistributing a firmware build.
