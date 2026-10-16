# Validation record

Validation performed 2026-10-10. This distinguishes compilation and simulation from physical hardware verification.

| Check | Result |
| --- | --- |
| S3 gateway build | PASS: ESP-IDF v5.5.4, ESP-Zigbee 2.0.4, UART-RCP / coordinator configuration |
| S3 link / image size | PASS: 0x10e8c0 bytes, 37% of the 1708 KiB application partition free |
| H2 RCP build | PASS: ESP-IDF v5.5.4, UART RX23/TX24, NCP vendor hook enabled |
| H2 link / image size | PASS: 0x32b60 bytes, 80% of the 1 MiB application partition free |
| SBC integration tests | PASS: 7 tests with actual localhost HTTP servers and temporary SQLite databases |
| Python syntax | PASS: compileall on source and tests |
| Dashboard JavaScript syntax | PASS: Node `--check` |
| README/local documentation links | Checked against included paths |
| Browser visual/interaction test | NOT COMPLETED: browser runtime download unavailable in this environment |
| Flashing, pairing, actual RF delivery | NOT TESTED: no physical board connected |
| 20–50 device network / soak | NOT TESTED |

Tests cover authenticated access, strict command validation, device/descriptor/report ingestion, On/Off forwarding through the simulator, event deduplication, gateway restarts, ring overflow gaps, database restart persistence, invalid ZCL measurement sentinels and rejection of commands while the gateway is offline. The simulator does not validate the real Zigbee stack, compatibility, radio timing or device firmware.

The build environment required a local ESP-IDF Component Manager process-inspection workaround for its container PID namespace. It changed the development environment only, not repository source or ESP-IDF APIs. CMake emitted deprecation notices for the newer local CMake version; project source compiled successfully. The distributed repository includes no toolchain/environment patch.

The API token is intentionally blank in defaults so unconfigured hardware fails closed. The compiled image used for validation is not distributed; users must configure their Wi-Fi and unique token before flashing. CI uses an explicitly named dummy compile token and does not upload deployable firmware.

Follow [operations](OPERATIONS.md) and [device compatibility](DEVICE_COMPATIBILITY.md) for the required hardware acceptance checks. Binding/report configuration, IAS enrolment, MQTT, automation rules, TLS and OTA remain documented future work.

## SBC API and locations update, 2026-10-12

- PASS: all 19 API/integration tests, including named-location CRUD, multi-device
  assignment, authentication, Unicode duplicate-name handling, limits, deletion
  conflicts, persistence across polling/restart and upgrading an existing database.
- PASS: published JSON Schema validation against actual simulator/SBC responses,
  contract export consistency, Python compilation and Git whitespace checks.
- PASS: two Chromium browser tests covering location creation, multi-device
  assignment, rename, unassignment/deletion, mobile width and logout during an
  in-flight refresh. JavaScript syntax checked with Node.

Browser validation used Playwright/Chromium with fonts and missing OS libraries
extracted into a temporary test environment on this SBC. Runtime remains Python
standard library only. The browser check in the original 2026-10-10 record above
was not performed at that time; this update supplies interaction coverage.
Firmware and physical Zigbee behavior have not been revalidated by this update.

## Raspberry Pi firmware development, 2026-10-13

The Raspberry Pi 5 is now the firmware development workstation as well as the
dashboard host. ESP-IDF v5.5.4 is installed at `/home/mark/esp/esp-idf`, with native
Linux ARM64 S3/H2 compiler tools and an isolated IDF Python environment. Fresh SSH
shells can load the tools with `. /home/mark/esp/esp-idf/export.sh`.

| Check | Result |
| --- | --- |
| S3 controller/API build on the Pi | PASS: ESP-IDF v5.5.4, ESP-Zigbee 2.0.4; image 0x10c9a0 bytes, 37% application partition free |
| H2 UART RCP build on the Pi | PASS: image 0x32b60 bytes, 80% application partition free; RX23/TX24 and vendor hook enabled |
| Native firmware regression tests | PASS: cursor limits/gaps/batching and cJSON command parsing, with undefined-behavior sanitizer |
| SBC/API integration suite | PASS: all 19 tests; contract-specific tests rerun after the event-query contract update |
| Exported API contract and Git whitespace checks | PASS |
| USB serial access | PASS: `/dev/ttyACM0` opens with the Pi user's `dialout` permissions |
| Connected chip identification | BLOCKED: USB device 303a:4001, serial 123456; no bootloader response using default-reset or USB-reset |
| Flashing, runtime API, Zigbee formation/pairing/control | NOT TESTED in this session |

Firmware changes fix uint32 cursor overflow, validate decimal event queries,
parse complete command bodies, reject duplicate fields and literal/escaped NULs,
and synchronize pairing health with stack permit-join notifications. S3 defaults
now select the USB Serial/JTAG console. Health and inventory routing also ignores
the query suffix when selecting the response type.

Both build outputs are local and Git-ignored. The S3 validation image has a blank
API token and placeholder Wi-Fi configuration; it is compile-only and will fail
closed on boot. Configure real credentials locally and rebuild before deployment.
No firmware was flashed or flash/network state erased. Physical bring-up requires
identifying which chip is connected, obtaining a bootloader response, checking
the existing network preservation requirement, and then flashing the matching
image. Native and simulator checks do not establish radio or device compatibility.

## Physical board bring-up, 2026-10-13

Both chips were subsequently identified and backed up before programming. USB2
is S3 revision 0.2, with 8 MB flash and 2 MB embedded PSRAM; USB1 is H2 revision
0.1, with 4 MB physical flash. Complete original flash images, verified saved-file
SHA-256 checksums, deployment image hashes and logs remain local in Git-ignored
`backups/`. The firmware retains the conservative S3 4 MB/H2 2 MB build profiles.

H2 RCP programming succeeded with all programmed image hashes verified. S3 Wi-Fi
credentials and a unique API token were configured locally, and programming also
verified every image hash. The first physical boot exposed a UART initialization
failure: IDF does not automatically register `/dev/uart` when using a USB console,
but the prebuilt Zigbee UART-RCP driver requires that registration. The application
now explicitly registers UART devices before Zigbee initialization for UART-RCP
with a non-UART console and declares its UART driver dependency. The corrected
build boots and forms the network successfully. A USB hard reset left S3 in ROM
download mode; an esptool 5.5 watchdog reset successfully started the application.

| Hardware check | Result |
| --- | --- |
| S3 Wi-Fi connection | PASS: joined the configured existing network and acquired a LAN address |
| S3/H2 UART-RCP handshake and network formation | PASS: formed a Zigbee network on channel 20 |
| Real health, device and event response schemas | PASS: validated against the exported gateway contract, including query-suffixed health/inventory and the maximum cursor |
| Authentication and input rejection | PASS: unauthenticated health 401; malformed/overflowing/repeated cursors and malformed/ambiguous command JSON 400 |
| Close pairing command | PASS: 202 stack acceptance; pairing remains closed |
| SBC poller against the physical gateway | PASS: hardware mode, connected/ready, and SQLite cursor persistence across store restart |
| Pairing, device discovery, RF reads/reports/control | NOT TESTED: device registry is empty |
| Coordinator reboot/network persistence and soak | NOT TESTED |

The hardware ingestion database is `data/hardware.sqlite3`, separate from demo
data. Credentials, databases and device backups remain Git-ignored. A successful
coordinator/RCP handshake and network formation do not establish interoperability
or delivery to a real Zigbee device; pairing a test device is the next check.

## Tabbed location dashboard, issue #8, 2026-10-13

- PASS: 29 API/integration tests, covering the existing v1 behavior and v2
  configuration, validation, cross-store revision conflicts, migration, seeded
  layouts, history pagination/filter binding, invalid samples, gaps, retention,
  schema/export consistency and persistence across service/store restart.
- PASS: eight Chromium interaction cases covering location tabs/lifecycle,
  widget creation/edit/removal/order/ranges, distinct endpoint sources, device
  reassignment, reload persistence, configuration conflict reapplication,
  step charts for reported state, stale/invalid/offline data, keyboard/mobile
  operation and logout during pending telemetry/history requests.
- PASS: JavaScript syntax, Python compilation, exported-contract consistency and
  Git whitespace checks. Browser validation used an isolated development
  environment with Chromium libraries/fonts extracted locally on the Pi.
- PASS: rehearsal and live migration of the existing hardware database preserved
  its device, two locations, assignment and all 17 events. Nine supported
  measurements were backfilled and four initial numeric/chart widgets created.
  SQLite integrity checks passed before and after deployment. Original database
  and deployed-code backups are local and Git-ignored.
- PASS: real LAN browser validation after service restart showed Configuration
  & Setup plus both location tabs, two numeric readings and two actual history
  charts for the assigned temperature/humidity sensor. Empty-location guidance,
  mobile width and logout passed without browser errors. Gateway polling remained
  connected and ready. This does not establish sensor reporting frequency or
  prove compatibility beyond the observed device/measurements.

Runtime continues to require only Python's standard library. The browser uses
native SVG charts and fetch; no CDN or chart-library installation is required.
Dense charts stop at 10,000 readings with a visible shorter-range notice. Fifty
devices, one hundred widgets and long-duration concurrent-client load have not
been load-tested. Firmware was not changed or reflashed for this dashboard work.

## Reporting commissioning, issue #10, 2026-10-15

- PASS: S3 build with ESP-IDF v5.5.4 / ESP-Zigbee 2.0.4, including remote binding,
  Configure/Read Reporting Configuration callbacks and a Poll Control client.
  Application size 0x1105f0 bytes; 36% of the application partition remains free.
- PASS: native firmware tests under undefined-behavior sanitizer for existing
  cursor/JSON logic, reporting policy limits/special intervals, response identity
  matching (address/endpoint/cluster/transaction), and timeout boundaries.
- PASS: all 36 API/integration tests. New coverage adds commissioning validation, authenticated HTTP,
  readback agreement/unsupported behavior, correlation after an uncertain HTTP
  submission, three-attempt limit, backoff/check-in wakeup, expiry, cancellation,
  policy persistence/reboot recovery and report/read-response origins.
- PASS: all ten Chromium cases. New coverage adds configure/cancel/retry/verified UI, recommended
  freshness, mobile width, logout and controls disabled on older firmware, while
  retaining all existing location/widget cases.
- PASS: complete fresh 8 MiB S3 backup and SQLite snapshot saved privately before
  deployment. Existing/built partition tables matched. Only the S3 application at
  0x20000 was flashed, with esptool hash verification and watchdog reset. H2,
  bootloader, partition table, NVS and Zigbee storage were not reprogrammed.
- PASS: application restarts retained PAN 0xebc5/channel 20, coordinator IEEE
  744dbdfffe67f12c, the paired SNZB-02WD registry entry, and closed pairing. The Pi
  service reconnected and advertises reporting commissioning support.
- NOT YET VERIFIED: the sensor did not answer the initial Poll Control binding
  requests (SDK transport timeout 7), and retries stopped at three attempts.
  No fresh sensor identity/readback/report has been claimed. Hardware validation
  requires waking/reaching the sensor, completing setup, observing unsolicited
  change-triggered and periodic reports over two maximum intervals, and checking
  recurring delivery after a subsequent coordinator restart. No manual reads were
  used to manufacture proof of unsolicited measurements.

Backups and deployment logs are local in `backups/issue10-20261015T111959Z/`.
Battery reporting and a general-purpose driver database remain out of scope.


### SNZB-02WD follow-up hardware observations, 2026-10-15

The sensor subsequently answered all seven commissioning steps with remote success,
including Poll Control and measurement bindings. Readback matched minimum 5 seconds,
maximum 3600 seconds, temperature delta 20 (0.2°C) and humidity delta 100 (1% RH).
Basic reads confirmed SONOFF / SNZB-02WD. Before the restart test, at least 20
temperature and 13 humidity unsolicited reports were recorded; their origin is
explicitly `report`, separate from manual reads. Dashboard freshness is now 4500 seconds.

A user-requested S3 restart test retained PAN 0xebc5, channel 20, coordinator identity
and the paired device. The initial reset did not promptly restore API access; a
second watchdog reset and startup inspection were needed before the gateway became
reachable again (final boot 145c9fc62f3766ce). No flash or network erasure was performed.
A fresh unsolicited temperature report was received in the final boot without
re-pairing. The automatic bounded reconfiguration workflow also resumed; some
requests timed out between sensor wake windows. Fresh unsolicited humidity reports subsequently also arrived after the restart.
The automatic reconfiguration attempt exhausted retries at Configure Reporting,
while both measurement streams continued using the previously verified policy.
Two-hour periodic-report observation is still pending. Restart evidence is
saved privately as restart-before.json / restart-after.json alongside deployment
backups. These observations do not establish accuracy against a reference sensor.


### Temperature-only endpoint follow-up, 2026-10-15

The newly paired Fish Tank device exposes endpoint 1 with temperature 0x0402 and
Poll Control 0x0020, but no humidity cluster. The original commissioning UI/API
incorrectly required both measurement clusters. The Pi now selects setup steps
from the discovered endpoint and accepts thresholds only for measurements it
supports. Existing combined sensor requests remain compatible; temperature-only
and humidity-only requests omit the unsupported change threshold.

All 38 API/integration tests and 11 Chromium cases pass, including single-measurement
job generation, readback, persistence, unsupported-threshold rejection and absence
of humidity controls/commands for a temperature-only device. Generated contracts,
Python/JavaScript syntax and whitespace checks pass. No firmware change or flash
is needed. The Pi service was restarted after a private SQLite/source backup and
queued four steps for the Fish Tank sensor: Poll Control bind, temperature bind,
configure and readback. The initial bind timed out; hardware acknowledgement and
unsolicited reports from that device remain pending a wake/reachability check.


The SNZB-02LD subsequently re-announced at a new short address and completed all
four temperature-only setup steps. Remote readback verified signed-int16 temperature,
minimum 5 seconds, maximum 3600 seconds and raw delta20 (0.2°C). An unsolicited
temperature report (raw1780 =17.8°C, RSSI -58dBm) was received and stored separately
from a subsequent read response. Fish Tank assignment was retained and dashboard
freshness is4500 seconds. Longer-term periodic delivery is still under observation;
no humidity operations were required. Private hardware-verification.json is saved
in the temperature-only deployment backup directory.


## Location-first navigation, issue #13, 2026-10-15

- PASS: all 15 Chromium cases, including four navigation cases for location-first
  connection/reconnect/reload, explicit Setup selection during refresh, empty-list
  onboarding, rename/deletion fallback, left/right alignment, long-name overflow,
  keyboard order across both groups, and logout/deletion during pending history.
  Existing sensor commissioning, widgets, chart editing and configuration conflicts
  retain their browser coverage.
- PASS: JavaScript syntax, generated-contract consistency and Git whitespace checks.
  This changes static browser assets only; API/database formats and firmware are
  unchanged.
- PASS: live Pi browser verification on desktop and 360px mobile. The first saved
  location opened after token connection, location tabs remained left-aligned,
  Setup stayed right-aligned, manual Setup selection survived refresh, keyboard
  Home returned to the first location, and reconnect again selected that location.
  Logout cleared authenticated content and no browser errors occurred.
- PASS: existing layout data, locations and assignments matched the predeployment
  snapshot, with SQLite integrity OK. Static assets were deployed after private
  source/database backup; no service or coordinator restart was required. Local
  evidence is in backups/dashboard-issue13-20261015T140719Z/.

## Issue #14 advance preparation, 2026-10-15

- PASS: 50 API/integration tests, including synthetic UL identity, reporting, battery, optional failures, scalar display readback, persistence, clock resynchronization and old-model regression cases. An additional targeted regression confirms observed UL identity cannot bypass the old-firmware gate with an empty hint.
- PASS: 18 Chromium browser tests, including three UL preparation cases and all prior dashboard regression cases.
- PASS: native C validation under undefined-behavior sanitizer and S3 ESP-IDF v5.5.4 build (image 0x111e10, 36% application partition free). H2 sources unchanged.
- NOT TESTED: physical UL pairing, RF timing, actual manufacturer framing/readback, sensor Time consumption, E-Ink effects and sustained reporting.
- Prepared S3 image is private because it contains deployment credentials. It has not been flashed as part of advance preparation.

See [the capability matrix and first-pairing checklist](SNZB_02UL.md). Simulator descriptors are synthetic, and remote/weather transport plus OTA remain explicit linked follow-ups.

## Issue #18 All sensors overview, 2026-10-15

- PASS: 23 Chromium dashboard browser tests during combined development with #14. The independently reviewable #18 branch additionally passes its 20 Chromium cases (five All-tab cases plus all 15 existing navigation/location/reporting/widget cases), with a targeted regression for saved device freshness on the existing API. #18 does not require the unmerged #14 backend.
- PASS: nine Playwright WebKit tests (All-tab and navigation suites), using the `iPad (gen 7)` touch/device profile. Coverage includes 390/507/768/1024/1180-pixel viewports, 200% page zoom, mixed sensor capabilities, 31 sensors, long names, stable nodes/scroll, API failure/recovery, no tile actions and no additional radio/history requests.
- PASS: live dashboard with both real sensors, initial-location default retained, All showing correct capability-specific readings, desktop/tablet portrait/landscape/narrow/mobile screenshots and no JavaScript errors. Saved layout, locations, assignments, freshness settings and commissioning records match the pre-change database snapshot; SQLite integrity is OK.
- PASS: JavaScript syntax, changed test Python compilation and Git whitespace checks. No API, database schema or firmware change was required for #18.
- PENDING: actual iPad Safari version/device verification, touch scrolling and text enlargement on hardware. WebKit device emulation is not physical Safari validation.

Local WebKit validation used downloaded libraries extracted into a private cache and software EGL rendering. Its cached launcher was adjusted to retain the library path; host-cache dependency validation was skipped because those libraries are outside the system cache. No system packages or repository runtime dependencies were installed/changed. These environment adjustments do not validate iPad-specific browser behavior.

See [All sensors overview](DASHBOARD_ALL.md) for operation and rollback. Optional browser engine/device selection is available via `DASHBOARD_TEST_BROWSER=webkit DASHBOARD_TEST_DEVICE='iPad (gen 7)'`; default browser tests continue to use Chromium.

## Issue #20 session-based user profiles, 2026-10-16

- PASS: 44 API/integration tests on the independent #20 branch, including six new profile cases; 56 on the combined live candidate with existing #14 preparation. Coverage includes existing-layout migration, restart persistence, concurrent contexts, revisions, invalid cookies, header precedence, deletion, duplicate names and limits.
- PASS: all 30 combined Chromium dashboard browser cases, including seven profile cases, plus a targeted final tablet-layout regression after the WebKit containment fix. Existing All/location/widget/reporting/UL behavior remains covered.
- PASS: seven profile cases in WebKit with an emulated iPad touch profile, covering simultaneous users, session-cookie restoration/blocking, shared-cookie tabs, late saves, management and long-name layouts at portrait/landscape/narrow widths. WebKit's native select text overflow was contained locally without clipping page content or weakening CSP.
- PASS: migration rehearsal against a copy of the actual configured hardware database: every existing table row and Admin's layout retained; only the profile table/Admin row added; SQLite integrity OK.
- PASS: generated contract consistency, JavaScript/Python syntax, unique combined HTML IDs and Git whitespace checks.
- PASS: live deployment with two independent browser contexts, separate preferences, session-cookie reload and four viewport screenshots; temporary validation profile removed. Admin configuration, shared metadata and database integrity preserved; gateway connected/ready with unchanged boot ID.
- PENDING: physical iPad Safari verification. Device emulation does not establish physical browser behavior.

See [user profiles](USER_PROFILES.md) for cookie lifecycle, shared versus personal settings, request-context handling, API and rollback. No firmware/network change is part of this feature.

## SNZB-02UL gateway preparation completed, 2026-10-16

- PASS: fresh S3 SDK build, application `0x111e10` bytes in a `0x1ab000`-byte partition (36% free); native cursor/JSON/reporting/sensor policy tests; 57 API/integration cases; six targeted UL/reporting Chromium cases; generated contracts and syntax/whitespace checks. V2 contract advanced to 2.4.0 for sensor extensions after the published 2.3 profile release.
- PASS: fixed and regression-tested observed-UL onboarding with an unspecified model hint: battery probes follow resolved device identity, while the user hint remains separate.
- PASS: USB identified S3 MAC `b8:f8:62:62:ff:08`; fresh full 8 MiB flash backup saved privately and size/hash recorded. The device partition table matched the fresh build exactly. Wrote only the factory application at `0x20000`; esptool verified its hash and used watchdog reset. Bootloader, partition table, NVS, Zigbee storage and H2 were not flashed/erased.
- PASS: live gateway ready with `sensor_extensions=true`, unchanged PAN `0xebc5` / channel 20 and both prior registered sensor IEEE/short addresses. Pairing remains closed. Invalid clock/vendor commands rejected with HTTP 400; valid Pi clock sync accepted and Time-service lease valid.
- PASS: live Pi connected/ready; location/assignment/device-settings/Admin-layout and all user-profile rows match the immediate pre-flash backup; SQLite integrity OK. Live browser checks retain both sensors, profile navigation, pairing controls and UL metadata without JavaScript errors at desktop/mobile widths.
- PENDING: genuine post-upgrade reports from sleeping devices and physical UL pairing/descriptors/manufacturer/display/Time-consumption/periodic-report acceptance. Both existing reporting-setup jobs show failed bounded rechecks; registration and historical measurements do not prove fresh RF delivery. No existing sensor has been reset or re-paired.

Firmware images, full flash backup, credentials, database snapshots and exact source hashes are private under the ignored backups directory. Sensor weather/remote-display transport and OTA remain the separate #16/#17 follow-ups; they are not advertised as ready for radio use.

## SNZB-02UL first physical pairing, 2026-10-16

- PASS: observed SONOFF / SNZB-02UL Basic identity, build 1.0.3 and endpoint/cluster descriptors; battery reads 100% / 3.2 V.
- PASS: all ten applicable setup steps acknowledged and reporting readback matched the actual saved 5/3600-second policy with 0.2°C / 1% RH changes; battery reporting readback also matched. Optional On/Off input cluster absent, so its binding was skipped.
- PASS: multiple real unsolicited temperature and humidity reports after setup. This supersedes the earlier unconnected-unit status for core telemetry only.
- PENDING: two maximum intervals, restart preservation/reporting, physical stale/offline behavior, display controls and Time consumption. Existing Garage/Fish Tank failed rechecks remain visible; their post-upgrade reports are not yet established. Remote/weather and OTA remain #16/#17.

## Issue #23 sensor signal history, 16 October 2026

- PASS: 63 API/integration tests, including six signal tests covering raw-event backfill, restart/idempotence, boot/sequence correlation, invalid/missing RSSI, non-attribute events, stale latest values after retention, bounded signed-cursor pagination, profile-specific signal widgets, authentication and schemas. Four contract cases rerun after the final schema formatting also pass.
- PASS: 33 Chromium browser cases across signal, All, UL, profiles, widgets, navigation, locations and reporting suites. Three initial failures were resolved: a new test's source selector was corrected, and automatic sensor-widget suggestions retain their previous measured-value behavior; users explicitly add RSSI widgets. All affected cases pass on rerun.
- PASS: eight WebKit cases with iPad touch emulation (signal and All suites), including 390/507/768/1024/1180-pixel widths, dense/long-name layouts, missing/stale signal, chart widgets and no controls/radio/history requests in All. Physical iPad Safari remains pending.
- PASS: migration rehearsal against the actual configured database: all pre-existing table rows unchanged, integrity OK; 465 retained RSSI-bearing events recovered at rehearsal. Immediate pre-deployment backup and migration recovered 470 samples, retaining all three real profiles and existing layouts/settings. Ongoing observations increased this count afterward.
- PASS: live dashboard service restarted and connected to the same gateway boot/network, with no firmware flash or sensor commands. All three physical sensor models expose real signal history; newly received RSSI is recorded. Garage now has post-upgrade unsolicited measurements, so its earlier pending-delivery status is superseded; failed commissioning-job state remains separate.
- PASS: live desktop/tablet/mobile All/Setup/location summaries and a browser-only real-data signal-chart preview (not saved into user layouts), no horizontal overflow, no JavaScript errors and GET requests only. Database/source backups, screenshots and validation logs are private under the ignored backups directory.

See [signal history](SIGNAL_HISTORY.md) for the dashboard-only source identifier, event association, 30-day retention and rollback. No firmware change is required.

## Issue #25 All dashboard layout, 16 October 2026

- PASS: 68 API/integration tests, including five All-layout cases covering default projection without database rewrites, older clients omitting the new field, invalid/atomic settings, If-Match conflicts, independent profiles, restart persistence and retained absent addresses. Generated API contracts and Git whitespace checks pass; v2 contract is 2.6.0.
- PASS: 38 distinct Chromium browser cases across the existing 33-case dashboard suite and five new All-layout cases (split runs). New coverage includes Auto and all 1–6 explicit counts, widths, rotation/Split View, ordering/new/departed/returning sensors, independent profiles, discard, conflict reapply and text enlargement. Final native-grid All/layout suites pass ten cases together.
- Grid sizing uses native CSS auto-fit/auto-fill with minimum widths and requested counts; this fixes a rotation/scroll jump found with an earlier delayed JavaScript sizing approach. JavaScript reports the effective count without resizing tracks after reflow.
- Startup rehearsal against the actual configured database preserves every existing table row and all three profiles, including their existing location widgets and saved signal history. No schema migration, firmware change or sensor command is needed.
- Physical iPad Safari remains pending; see the issue record for WebKit emulation and live deployment results.


- PASS: ten distinct WebKit/iPad-emulation cases across final All-layout and All suites (split runs). Reload coverage now uses the standard UL simulator directly; an intercepted battery-fixture request during navigation caused a test-only access-control error in an earlier run. All five layout cases pass together with the direct fixture, and the five existing All cases pass with native grid sizing.
- PASS: live Pi deployment retained every existing table row at startup, all three profiles and their 14/14/0 location-widget counts. Defaults remain Auto/240/empty-order. SQLite integrity OK; Pi service connected/ready with the same gateway boot, and no firmware change.
- PASS: live browser inspected all three real sensor tiles, Setup controls, one-through-six requested columns, reversed-order previews, 1180/768/507/390-pixel widths and reload. All requests were GET, no preview was saved into user profiles, no JavaScript errors or horizontal overflow; actual sensor telemetry and RSSI remain visible. Private snapshots, screenshots, logs and source hashes accompany deployment.

See [All layout settings](ALL_LAYOUT.md) for width/count precedence, order retention, profiles, API compatibility and rollback.
