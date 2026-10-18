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

## Pi access loss and persistent incident logs

Loss of SSH/dashboard access can be a Wi-Fi disconnect, upstream router outage, service failure or Pi lockup. A later manual power-cycle explains the new boot and unclean-shutdown flag; those observations do not identify the initial failure. On 18 October the user confirmed manually power-cycling the Pi to recover access. Its previous-boot logs were lost because the OS vendor journald drop-in selected `Storage=volatile`. The original Wi-Fi-versus-lockup cause remains undetermined; current healthy memory/temperature or `get_throttled=0x0` cannot exclude a pre-reboot problem. The Pi 4 Rev 1.2 reset register is not a definitive external-power-loss diagnosis.

If another access method remains available, collect evidence before restarting:

```bash
uptime
ip -br address
ip route
iw dev wlan0 link
systemctl --user status zigbee-dashboard.service --no-pager
journalctl -b -u NetworkManager --since '30 minutes ago' --no-pager
journalctl -b -k --no-pager
journalctl --list-boots
systemd-analyze cat-config systemd/journald.conf
```

The user-service command applies to this project's existing user-service deployment; installations using the documented system service should inspect that unit instead. Preserve logs privately, including when access failed and whether recovery involved a manual reboot. Kernel uptime/monotonic timestamps can help when NTP changes the boot's initial wall-clock timestamps. Do not open the ESP USB console to investigate a Pi Wi-Fi issue: on this hardware that can reset the gateway and confound the evidence. Do not test recovery by switching a plug that supplies the Pi/router or a required network link.

An administrator can optionally enable bounded persistent logs for the **next** incident. This is documentation, not a configuration change made by the dashboard or this documentation update. Check existing drop-ins first; retain any prior local override for rollback. Create `/etc/systemd/journald.conf.d/60-zigbee-incident-logs.conf` with:

```ini
[Journal]
Storage=persistent
SystemMaxUse=100M
SystemKeepFree=500M
SystemMaxFileSize=10M
RuntimeMaxUse=32M
MaxRetentionSec=7day
SyncIntervalSec=30s
```

Apply and inspect locally with administrator privileges:

```bash
sudo systemctl restart systemd-journald
sudo journalctl --flush
systemd-analyze cat-config systemd/journald.conf
journalctl --disk-usage
journalctl --list-boots
```

The override must win over the vendor's volatile-storage setting. Size/age policies rotate archived files; active-file granularity can exceed the target. The shorter sync interval adds writes and reduces, but does not eliminate, the unflushed tail lost on abrupt power removal. After a later reboot, `journalctl -b -1` can inspect the prior boot only if it was actually retained. None of this recreates logs already lost. To roll back, restore/remove only this project's local drop-in, restart journald and inspect the effective configuration; changing storage mode does not delete existing disk logs. See the primary [journald configuration](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html) and [journalctl](https://www.freedesktop.org/software/systemd/man/latest/journalctl.html) references. Do not publish raw journals, tokens or household identifiers.

## Smart-plug operation and mesh checks

Use [S60ZBTPG controls](S60ZBTPG.md) and inspect job acknowledgement/readback rather than assuming HTTP acceptance changed the outlet. Relay On means the outlet supplies the attached load; a zero reading can still be genuine with no active load. Inching is device-side timed switch-back and may be left disabled for continuous loads. Power-loss behavior, protection enable and protection thresholds are separate settings. Correct thresholds before enabling protection and verify both; changes apply to one unit only. Never demonstrate protection by intentionally overloading mains equipment.

Powered S60ZBTPG units are router-capable, including with their output relay Off. Place them where they can reach other mesh nodes, rather than concentrating every router beside the coordinator. Relocation may change link quality, but RSSI records received messages and does not identify a sensor's parent or complete route. Keep existing sensors paired while observing; no route improvement or topology is established by this project's current API. Actual paths and longer-duration delivery remain acceptance work. The [hardware record](HARDWARE_VALIDATION_2026-10-18.md) identifies completed checks and limits.
