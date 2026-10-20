# Validation record

## Current evidence index

See [18 October 2026 hardware validation](HARDWARE_VALIDATION_2026-10-18.md) for the three S60ZBTPG units, completed reporting/switching/settings/restart checks, scoped iPad acceptance and Pi incident limitations. Older entries below are historical milestone records; statements such as “hardware pending” describe the evidence at that milestone, not a claim that no later testing occurred. The current product guides and dated record identify remaining work.

## Radio dashboard, issue #50, 2026-10-20

- PASS: ESP32-S3 gateway build with ESP-IDF 5.5.4 / ESP-Zigbee 2.0.4. The
  authenticated radio endpoint reads coordinator-local neighbor, route and
  source-route tables with 64-entry bounds while holding the Zigbee stack lock.
- PASS: native firmware regression tests and Python simulator/API tests for
  schema-valid radio snapshots, cached status, unsupported old firmware and
  stale snapshot handling. The simulator's radio entries are synthetic.
- PASS: dashboard unit tests and production Vite build; built assets include the
  lazy-loaded Radio tab. API contract exports and Python compilation pass.
- NOT COMPLETED: browser interaction acceptance. Chromium can launch with the
  locally extracted libraries, but the existing browser fixture did not submit
  the access-token field in this runner, so no visual/responsive result is
  claimed for the Radio page.
- PASS: deployed the built S3 application on 2026-10-20 after saving a full 8 MiB
  flash backup and confirming the existing partition table matches the build.
  Only the factory application at `0x20000` was flashed and verified; bootloader,
  partition table, NVS/Zigbee state and H2 radio firmware were preserved. The
  gateway returned authenticated health with `ready=true`, and authenticated
  `/api/v1/radio` returned five coordinator-local neighbor entries. The live
  dashboard returned `status=available` from `/api/v2/radio` and retained all
  six registered devices. This verifies API operation and retained access-token
  authentication, not route accuracy or complete topology.
- NOT TESTED: physical radio table population, live route accuracy, iPad Safari
  layout for this tab, channel utilization, noise/interference, and Zigbee
  retries/delivery counters.

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

The API token is intentionally blank in defaults so unconfigured hardware fails closed. The compiled image used for validation is not distributed; users must configure their Wi-Fi and unique token before flashing. There is currently no GitHub Actions workflow in this repository; validation is run locally.

Follow [operations](OPERATIONS.md) and [device compatibility](DEVICE_COMPATIBILITY.md) for the required hardware acceptance checks. At this milestone, binding/report configuration was future work; it has since been implemented for supported profiles. IAS enrolment, MQTT, automation rules, TLS and OTA remain subject to the current roadmap and model-specific capability records.

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

The Raspberry Pi (later identified as a Pi 4 Model B Rev 1.2, despite its hostname) is the firmware development workstation as well as the
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

## Issue #28 continuous Wi-Fi recovery, 17 October 2026

- PASS: final S3 SDK build, application 0x1131a0 in the unchanged 0x1ab000 factory partition (36% free); native C policy/cursor/JSON/reporting/sensor tests under undefined-behavior sanitizer. Network policy tests exercise 100,000 failures over more than seven simulated days, saturation, deadlines, duplicate disconnect handling and guarded reboot eligibility.
- PASS: 76 API/integration cases, including eight network cases for nonce/HMAC/identity verification, persisted endpoint bindings, bounded discovery, wrong-host responses, authentication failure, uncertain write handling and buffered-measurement/RSSI ages. An old buffered sample remains stale; raw Pi receipt and inferred gateway receipt time are distinct. Generated contracts match (v1 1.6.0, v2 2.7.0).
- PASS: eight Chromium network/reporting/navigation cases, plus the final network case rerun with explicit cached/offline diagnostics. Live browser at 1180/768/390 pixels shows healthy recovery diagnostics and all three real tiles without overflow, JavaScript errors, credential exposure or non-GET requests.
- PASS: fresh full 8 MiB S3 backup and private configuration/database/source snapshots; partition table matched. Only the application was flashed; bootloader, NVS/Zigbee storage and H2 were preserved. Initial live testing found HTTP readiness incomplete in the first candidate. The corrected image moves listener startup/repair under the network worker after IP readiness and retains IPv6 link-local initialization. Final image health/API/Zigbee are ready.
- PASS: bounded 180-second unavailable-SSID test invoked solely through the #28 worker. API and Pi offline state were observed, then both recovered automatically in 182.24 seconds total. Before/after boot ID remained 8083ad04b2f30628, with 11 connection attempts during the test, zero radio/listener restarts and no recovery reboot. No manual Wi-Fi/USB reset was used to pass the outage test.
- PASS: network PAN/channel and all three registry entries unchanged; settings, locations, profiles and layouts match the pre-test snapshot, SQLite integrity OK. Three genuine UL attribute reports received by Zigbee during the outage were buffered and drained afterward, demonstrating continued Zigbee operation. This is not a claim that all sleeping sensors emitted within that three-minute interval.
- PASS: actual LAN authenticated discovery recovered a deliberately stale endpoint on the same known gateway (closed port), and its verified endpoint persisted across a client/store restart. The real Pi retained its binding through service restart. This tests rediscovery, not a physical DHCP lease change. Invalid durations/types returned 400, missing/wrong authentication returned 401 and unauthenticated discovery was ignored.
- Diagnostic console read used raw CDC-ACM without modem-control or termios changes; discovery remained continuous (102 replies, maximum interval 0.45 s), establishing no reset during that read. Application deployment boots are distinct from autonomous recovery evidence.
- PENDING: physical cold boot with AP absent, actual AP/router reboot, changed DHCP lease, repeated and overnight-length outages, and deliberately forced internal-driver/listener/worker-stall escalation. Native tests and a three-minute injected outage do not substitute for those extended scenarios; issue #28 remains open.

Private evidence is in the ignored wifi-issue28 backup directory; the final recovery-image manifest identifies the deployed image. The optional authenticated validation hook is enabled in this deployment's private sdkconfig and defaults off in source configuration. See [Wi-Fi recovery](WIFI_RECOVERY.md).


## Issue #27 S60ZBTPG preparation (18 October 2026)

- Pinned primary converter protocol at 72398c3063aca492fe936bf01e0a5fffad28fbd1 and manufacturer codes at cf29e23a3c0fbfcbad9cb5c6694448381b6f61ba; capability/acceptance matrix in S60ZBTPG.md.
- 88 API/integration tests passed (12 plug preparation cases plus 76 existing regressions). Native C sanitizer tests cover plug payloads/flags/checksums/product limits/report types alongside cursor/JSON/sensor/reporting/network policies. SDK build produces 0x115530-byte application, 35% partition free.
- 26 distinct Chromium cases passed across runs (a profile reload fetch failure passed its targeted rerun); three final WebKit iPad emulation cases passed with the cached Mesa runtime. Chromium plug cases exercise shared durable operations, readback, raw Off telemetry, data-only All tiles and responsive sizes; existing All/layout, reporting, UL and profile cases are also run. WebKit iPad emulation is separate from physical iPad Safari acceptance. Tablet testing found and corrected replacement of live location buttons during polling; their DOM identity is retained.
- Migration rehearsal preserves every row in all 17 pre-existing database tables and passes integrity checks. Synthetic plug fixtures are isolated from the hardware registry. No physical plug compatibility, protection trip behavior, period boundaries, router path or inching timing is claimed.
- OTA is explicitly deferred to #30; schedules/countdowns/scenes and device timing verification to #31. Parent #27 remains open. Exact logs, backup/source/image manifests and live deployment checks are private under the ignored backups directory.


## Hardware follow-up and documentation reconciliation — 18 October 2026

- Three S60ZBTPG build 1.0.2 units each verified 34/34 setup steps. Actual device evidence now includes unsolicited electrical reports, a physical button/state transition, remote Off/On acknowledgements with matching readback on one unit, selected LED/startup writes and a 13 A / 3250 W protection configuration followed by enable readback on one unit.
- The user-requested gateway restart preserved network/registry and the first plug's On state; electrical reporting resumed without recommissioning. Relocated plugs reconnected. This does not establish the full plug power-loss or mesh-route acceptance.
- Earlier All/profile/RSSI/layout physical iPad acceptance is recorded in closed #18/#20/#23/#25, with no version or detailed interaction results inferred. New plug physical Safari acceptance remains open.
- After a later loss of Pi access, the user manually power-cycled the Pi. Prior logs were volatile, so the original cause remains undetermined. Wi-Fi/dashboard/gateway recovery after that cycle is not proof of same-boot autonomous Wi-Fi recovery.
- Private job/report/backup artifacts were checked before writing the sanitized public summary. Credentials, household identifiers, raw journals and backups are excluded from Git. No firmware, service, network, logging configuration or relay changes are part of this documentation update.

## Dashboard #34 All design prototype, 19 October 2026

The All prototype uses React/Mantine/GridStack and an isolated configuration snapshot for live-data review, leaving the existing dashboard service and gateway untouched. See [migration scope](DASHBOARD_MIGRATION.md). Current API regression checks and new layout/frontend tests are recorded separately from browser and hardware acceptance. Six real devices rendered at desktop/tablet/phone widths without horizontal overflow or page errors using GET-only traffic; no radio commands or history queries were sent by viewing All. Visual acceptance, physical iPad testing and subsequent location/full Setup implementation remain pending; #34 stays open.

Prototype verification: **93 API/integration tests**, **4 frontend layout/semantics tests**, **7 Chromium browser cases** and **7 WebKit iPad-emulation cases** passed. The browser cases cover responsive read-only rendering, mouse drag/save, numbered geometry controls, theme/reload/discard, conflict/reapply, profile switching/deletion, disconnect cleanup and departed/returning devices with stable polling nodes. A real iPad's finger gestures are not established by emulation. Production build, frontend formatting, Python compilation, exported contract consistency, local Markdown links and whitespace checks passed. No firmware compilation/deployment was needed because no firmware changed. The bundle is approximately 565 kB JavaScript and 266 kB CSS before compression; third-party notices are supplied separately.

### Location navigation follow-up, 19 October 2026

Following user feedback, location tabs now stay inside the React preview, displaying saved numeric/chart widgets in configured order, or current assigned-device tiles when the profile has no saved widgets. History GETs are forwarded to the installed dashboard with authentication; action routes remain disabled. Identical chart sources/ranges share bounded queries, and leaving a location aborts pending history work. Six frontend tests, three targeted API/asset tests, three targeted Chromium cases and three targeted WebKit iPad-emulation cases passed. Live GET-only checks opened all four locations on the preview origin, loaded saved history, and returned to All without overflow/page errors. Only the separate preview service restarted; production dashboard, device settings and firmware were untouched. Full Setup, location widget editing/control migration and physical iPad acceptance remain pending.

### Primary dashboard replacement, 19 October 2026

On the user's instruction, the replacement now serves `/`, with the old HTML/controller/CSS removed and `/next/` redirecting to the primary page. React/Mantine implements Setup, device reporting/display/plug controls, metadata/profile management and widget editing; GridStack stores independent All/location screen geometry. Old DOM-specific browser suites were replaced with workflow coverage for the new interface.

Verification: **95 API/integration tests**, **8 frontend tests**, production build, contracts, Python compilation, formatting and documentation links passed. **16 distinct Chromium and 16 distinct WebKit iPad-emulation cases** were exercised across full and targeted runs, rather than claimed as one combined final run. Final targeted checks cover configuration conflict/reapply preserving unrelated location geometry, metadata management and asynchronous reporting-policy loading without overwriting edits. Device-action cases use synthetic fixtures; live installation checks remain GET-only. The default iPad viewport is tablet-sized, so the location-layout test explicitly selects Desktop before asserting desktop geometry.

The user confirmed the framework/navigation works and explicitly said the appearance is too similar to the original. Visual design acceptance is **not** claimed: a distinct redesign is tracked in #35. Physical iPad model/version, finger gestures, orientation and complete accessibility acceptance remain outstanding in #34. Deployment preserves current history/configuration and requires only the Pi dashboard restart; no firmware/network deployment is part of this change.


## Dashboard appearance and editing — 19 October 2026 (#37–#40)

The development build combines widget/content scaling, discoverable tab layout editing, saved metric typography and the Grafana-inspired Observatory panel design. It uses the existing renderer and dependencies; Grafana is not a runtime/build dependency.

- PASS: 97 Python API/integration cases, including bounded presentation validation, invalid/NaN/type rejection, atomicity, ETags, profile isolation, old-client omission preservation and reopening stored preferences.
- PASS: 14 frontend layout/history/presentation cases, including sparse overrides, reset/inheritance, contrast, gap-aware fills and preserving concurrent changes to unrelated style fields, screen geometry and theme.
- PASS: 20 distinct Chromium and 20 distinct WebKit iPad-emulation browser cases across initial full and subsequent targeted runs. Initial runs: 16 Chromium plus three new typography/navigation cases, and a combined 19 WebKit cases. Final targeted runs cover history bounds/cache/hidden-page behaviour, conflicts, drag geometry, location navigation, font preview/save/reset, profile defaults/contrast and responsive rendering. This is not claimed as one combined final 20-case run.
- PASS: production build, API contract export/check, Python compilation, Prettier, local Markdown links and whitespace checks. Vite retains its existing >500 kB core-chunk advisory; no new dependency was added.
- PASS: live GET-only review with six devices and four locations; no page errors or horizontal overflow at 1440×1000, 1024×768, 768×1024 and 390×844. Production configuration/profile/device metadata/location/assignment rows matched the private pre-review backup; SQLite integrity remained OK.
- PASS: preview-only API save of typography followed by preview service restart restored the exact preferences. The temporary validation profile was removed afterwards. The production dashboard/gateway were not restarted for this check.

A short Pi Chromium smoke comparison recorded current/preview ready times of 1.49/1.64 seconds and JS heaps of approximately 6.38/6.84 MB; a repeat under concurrent browser tests recorded 2.54/2.95 seconds and 6.41/6.75 MB. These are small local observations, not a controlled performance benchmark or an extended memory soak. The preview made six initial bounded history requests and none in the next five-second observation window. All history has a 60-second minimum cache, two-query concurrency and 120-sample response bound per device; hidden/departed history work is cancelled. The main JS bundle grows from about 609 kB to 636 kB (roughly 4.4%); CSS grows from about 270 kB to 275 kB. Node remains build-time only.

The initial review instance on port 8081 used a private database snapshot and read-only forwarding of live state/history. The user subsequently accepted the build and requested primary deployment, commit, PR and merge. The approved build now serves the normal port 8080; the review instance is stopped. Production history and metadata are retained, with only reviewed presentation preferences reconciled separately when changed. Safe synthetic screenshots are included in the repository. API 2.10.0 adds bounded optional presentation settings; see [appearance and editing](DASHBOARD_APPEARANCE.md).

User visual acceptance: confirmed explicitly with “im happy with the build”. The user subsequently confirmed that physical iPad checks are complete and the dashboard works well. WebKit device emulation remains recorded separately from this physical acceptance. Extended performance observation remains open under #40. Deployment restarts only the Pi dashboard service. All live review requests were GET-only; the persistence probe changed only the isolated preview configuration. No firmware, Zigbee/reporting, relay, protection or Pi Wi-Fi settings were changed.

Primary cutover verification: the normal port 8080 served all six devices, all four location pages, history and Setup, with no page errors or horizontal overflow at the four documented viewports. Browser checks issued GETs only and made no port 8081 handoffs. Device/location/assignment rows and profile registry were unchanged; widget/title/unit/legacy-layout preferences were preserved, measurement count did not decrease and SQLite integrity was OK. Only reviewed presentation fields were migrated through the configuration API using its ETag. The primary service was restarted once; the preview service was stopped.

## Dashboard iPad acceptance — 19 October 2026

- PASS (user-confirmed): physical iPad checks are complete; the deployed dashboard works well on an iPad.
- The specific iPad model and Safari version were not recorded in this repository. WebKit emulation remains separately identified and is not used as evidence for the physical checks.
- Extended performance observation remains outstanding; see issue #40. The dashboard is deployed on port 8080 as documented in [dashboard appearance](DASHBOARD_APPEARANCE.md).
