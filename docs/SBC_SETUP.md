# SBC service setup

Use Raspberry Pi OS Bookworm or newer, Debian 12+, or another Linux distribution with Python 3.11+. In this project the Pi is both the dashboard host and the ESP firmware development workstation. The dashboard service uses Python's standard library and requires no package install; firmware development uses the separate ESP-IDF toolchain.

## Manual run

Copy `.env.example` to `.env`, generate two distinct tokens and edit the URL. Source the environment with `set -a; . ./.env; set +a`, then `python3 -m sbc.app` from the repository root. Source only your own trusted environment file, since it is shell code. Use localhost:8080 by default.

For remote access without changing the bind address:

```bash
ssh -L 8080:127.0.0.1:8080 pi@YOUR_SBC
```

Then open localhost:8080 on your laptop. For direct trusted-LAN access, set `BIND_HOST=0.0.0.0` and restrict incoming TCP 8080 to your clients.

## Optional systemd service

Install the repository at `/opt/zigbee-border-gateway`, readable by the service user. Example on Debian/Pi OS:

```bash
sudo useradd --system --home /var/lib/zigbee-gateway --shell /usr/sbin/nologin zigbee
sudo cp .env.example /etc/zigbee-gateway.env
sudo chmod 600 /etc/zigbee-gateway.env
sudoedit /etc/zigbee-gateway.env
# Set the real board URL, both tokens and a suitable bind address.
sudo cp sbc/gateway.service /etc/systemd/system/zigbee-gateway.service
sudo systemctl daemon-reload
sudo systemctl enable --now zigbee-gateway
sudo journalctl -u zigbee-gateway -f
```

Systemd reads the root-owned environment file before dropping privileges. It overrides DB_PATH to its managed state directory. Do not run the simulator as the production gateway. Use DHCP reservations for the board and SBC, synchronized time and regular SQLite backups.

## Connecting your own dashboard

The built-in dashboard supports dynamically named locations. Connect, add a
location such as Kitchen or Greenhouse, then use each device's Location selector.
Several devices can share a location; renaming it preserves all assignments.
Location editing works while the ESP32 is offline. Move or unassign all devices
before deleting a location. Names and assignments are stored in the same SQLite
database as device/history data and are included in its backups.

Location tabs sit on the left of the navigation bar; **Configuration & Setup**
is separate on the right. Connecting with the token opens the first saved location
in the displayed order, including an empty location. Reconnecting or reloading
uses the same rule. Setup opens automatically only when there are no saved
locations. Select Setup explicitly for configuration; polling preserves your
selection. If the selected location is deleted, the first remaining location
opens, or Setup when none remain. Location tabs scroll independently on narrow
screens so Setup remains reachable; arrow keys, Home and End follow the visible
order of locations then Setup.

Configuration & Setup contains pairing, inventory, locations, device names and
freshness settings. Every location has its own tab with editable numeric readings
and history charts. Use Add widget to select a device endpoint measurement, or
Add sensor widgets to create numeric/chart pairs for the available sources.
Titles, ordering, temperature display units and chart ranges persist on the Pi.
Widgets follow devices when their locations change. On the first upgrade,
already assigned sensors receive initial numeric/chart widgets; intentionally
deleted widgets are not recreated on subsequent starts.

Charts use stored measurements with receipt timestamps, not browser-generated
samples. Ranges are one hour, six hours, one day, seven days and thirty days.
Known ingestion interruptions, invalid readings and freshness gaps break chart
lines. Freshness defaults to one hour and can be changed per device. Gateway
offline status is independent of the age of a saved reading. No tab requests
a radio read unless a user explicitly uses a Read control in Setup.

When two browser sessions edit configuration, a stale save displays a conflict.
Reload to discard it, or choose Reload & reapply edit to apply the specific edit
to the latest revision. Existing v1 location mutations also advance that revision.
Back up the SQLite database before upgrading. Opening an existing database adds
the configuration/history tables and backfills retained attribute events once.

Call SBC `/api/v1/state` for the persistent projected registry. Send commands to `/api/v1/commands`. Your dashboard backend may instead call the board API directly with GATEWAY_TOKEN. The board has no browser CORS support, history database or dashboard. It does not ship with this project's API until you flash our S3 firmware.

For paired temperature/humidity sensors, open **Configuration & Setup → Sensor
reporting setup**, select the user-reported model if known and configure reporting.
Briefly wake the sensor as requested. Check acknowledgements/readback, then observe
unsolicited reports across at least two maximum intervals. See
[compatibility and reporting](DEVICE_COMPATIBILITY.md) for retry, expiry and
verification semantics. Existing gateway firmware must be upgraded before these
controls become available; no re-pairing or network erasure is required.

## All sensors overview

Select **All** after connecting to view compact, read-only tiles for every discovered sensor, including unassigned sensors. See [overview behavior and tablet validation](DASHBOARD_ALL.md). Existing location widgets and the first-location login default are retained.
