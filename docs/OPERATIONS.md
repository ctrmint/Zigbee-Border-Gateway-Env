# Operations and recovery

## Routine checks

Check health, latest report timestamps and `dropped_events`. Registered is not synonymous with online. Battery sensors legitimately sleep; choose freshness thresholds by model. The UI retains old values with receipt timestamps. Firmware timestamps are uptime; SBC receipt timestamps require a correctly synchronized clock.

## SBC outage

Board Zigbee network continues operating, but event history is bounded and SBC rules are not present. Restore SBC networking and inspect the gap indicator. Registry sync restores device membership; rediscover devices if descriptors were missed. Never replay queued actuator commands after recovery.

## Gateway reboot / radio failure

S3 restores SDK network state and its small registry from NVS. Pairing stays closed. Retained short addresses are last known addresses; announcements reconcile them. If commands fail, wake devices and rediscover/rejoin as appropriate. The host's upstream RCP integration handles the serial interface, but no custom watchdog/automatic RCP reflashing is enabled here. Check the H2 version/log and matching 460800-baud UART pins.

## Backups

SBC database backup:

```bash
python3 - <<'BACKUP'
import sqlite3
source = sqlite3.connect('data/hardware.sqlite3')
target = sqlite3.connect('hardware-backup.sqlite3')
source.backup(target)
target.close()
source.close()
BACKUP
```

Protect the backup: it contains device identifiers and household activity. This backs up application history, not the Zigbee network/security state. No safe Zigbee network backup/restore tool is provided. Do not erase S3 flash/NVS unless deliberately rebuilding the network and accepting re-pairing. Frame counters and keys make raw flash restoration security-sensitive.

Raw event retention is 30 days, pruned periodically while polling succeeds. Latest attributes remain in device projections. Tune retention only after measuring storage usage. Database vacuuming is manual; run while the service is stopped if reclaiming disk is needed.

## Test plan on hardware

- Verify both chips and RCP version; retain serial logs without secrets.
- Pair a router plug and standard sensor, read model/manufacturer, inspect descriptors.
- Toggle and verify reports/read-back plus physical state.
- Reboot board, SBC and access point independently; confirm no unwanted pairing/command replay.
- Test sleepy device interviews and short-address changes.
- Grow through 5, 20 and 50 devices; measure heap, RF failures, discovery failures, ring gaps and read latency during Wi-Fi traffic.
- Observe a 24-hour soak before enabling unattended use. This source does not implement a safety controller for heaters, locks or other critical loads.

## Reporting setup and stale sensors

A connected gateway and a registered device do not prove recurring measurements.
For a discovered temperature/humidity endpoint, use **Sensor reporting setup** in
Configuration & Setup. Briefly wake the sensor as instructed by its manufacturer.
The action binds measurement clusters and, if advertised, Poll Control to the
coordinator endpoint 10, then configures and reads back reporting settings.

Inspect the acknowledgements/readback panel. A local 202 only means accepted;
`verified` requires successful remote responses plus matching settings. Unsupported
readback is `configured_unverified`. Transport timeout 7 indicates no response;
check wake state, battery and range, then explicitly retry after a failed/expired
job. Automatic retries stop at three per step or five minutes. Cancellation cannot
undo packets already sent, and a bounded fast-poll window may remain briefly.

Watch temperature/humidity values labelled **report**, rather than **read response**
or **unknown**, across two maximum intervals before declaring recurring reporting
working. For the SNZB-02WD reference hourly policy, use a freshness margin such as
4,500 seconds; the dashboard offers this after verified setup. Do not increase the
threshold to disguise missing reports. Keep the existing network and pairing;
factory reset or network erasure is not a commissioning troubleshooting shortcut.
