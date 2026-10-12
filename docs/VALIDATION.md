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
