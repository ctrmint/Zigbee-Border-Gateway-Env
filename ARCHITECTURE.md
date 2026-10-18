# Architecture

## Decision

Use the Espressif S3/H2 gateway board as a **Zigbee coordinator**, with an SBC as the application host. The name “Thread Border Router” describes the hardware's other intended use; this repository flashes Zigbee firmware and does not provide simultaneous Thread border routing.

```mermaid
flowchart TD
    B["Browser dashboard"] -->|"Authenticated REST"| S["SBC: API, registry and history"]
    S -->|"REST over local Wi-Fi"| G["ESP32-S3: coordinator and Trust Centre"]
    G <-->|"Onboard UART / Spinel"| H["ESP32-H2: 802.15.4 RCP"]
    H <--> R["Mains-powered Zigbee routers"]
    R <--> E["Battery end devices"]
    H <--> E
```

| Component | Responsibility | Persistent state |
| --- | --- | --- |
| H2 | Radio/MAC, frame transmission and reception | RCP image; no application registry |
| S3 | Zigbee coordinator/Trust Centre, commissioning, discovery, ZCL, local API | SDK network/security state in NVS and a separate IEEE/NWK registry |
| SBC | Dashboard API, device projection, raw events and normalized values | SQLite database and polling cursor |
| Browser | Display and user controls | Token only in page memory; presentation profile ID in a session cookie |

## Physical and RF design

S3 Wi-Fi and H2 802.15.4 use separate radios. This removes the single-C6 radio time-sharing bottleneck. Both still occupy 2.4 GHz: antenna coupling and nearby Wi-Fi can cause interference. Board PTA wiring is available, but this MVP does not enable or validate external coexistence. Choose channels and location deliberately; Ethernet support is a future firmware configuration, not enabled in this release.

The supplied S3 UART mapping is RX GPIO17 and TX GPIO18 at 460800 baud. H2 RX GPIO23 and TX GPIO24 match the onboard wiring. GPIO7/8 are reset/boot control lines; this MVP flashes H2 directly and disables automatic RCP updates. Do not attach LED/button code to those reserved pins.

## Data flow

1. S3 forms or restores its network, with joining closed.
2. An authenticated permit-join request opens a short commissioning window.
3. Device announcements provide IEEE and current NWK addresses. The IEEE address identifies a device across short-address changes.
4. S3 requests active endpoints and simple descriptors. Descriptor events contain input/server and output/client clusters.
5. ZCL reports/read responses become raw attribute events. Supported scalar types and character strings are copied before callback buffers expire.
6. SBC polls the 64-event ring, commits raw events, device projections and its cursor in one SQLite transaction.
7. Measurements are normalized only for supported identities, clusters, attributes and ZCL types. This includes temperature/humidity, observed battery values and S60ZBTPG metering with validated units/scaling. Raw values remain separate and invalid sentinels remain unavailable. Buffered event ages use same-boot gateway uptime estimates when available.
8. UI sends a command to the SBC, which validates and forwards it. The board locks the Zigbee stack before calling its APIs.

## Reliability and semantics

- `(boot_id, seq)` deduplicates events; a new boot resets the cursor. The S3 event ring is volatile and limited; outages may lose history. The current gap indicator is retained for the SBC process and recording interruptions are also persisted in SQLite for history views.
- The SBC syncs the persisted board registry on every poll, recovering missed membership changes. Lost descriptors need rediscovery; lost historical reports cannot be recreated.
- Wi-Fi recovery and API listener lifecycle are owned by the network worker after IP readiness, independently of Zigbee startup. Commands return 503 until formation/restoration is complete.
- HTTP 202 means the stack accepted a request. It does not confirm RF delivery or a changed actuator state. Legacy generic commands expose acceptance and telemetry. Dedicated sensor/display/plug jobs correlate responses by request ID, source, endpoint, cluster and transaction sequence; readback verifies expected settings/state without optimistic relay updates.
- Uncertain load/settings writes are never automatically replayed. Dedicated bounded workflows may retry reads, binding or reporting operations; a Pi process restart cancels unsent plug load/settings jobs and marks in-flight ones uncertain. API readiness/identity checks and durable job semantics remain separate from physical state.
- Existing Zigbee routers continue routing when the SBC is unavailable. SBC automations are not implemented. Gateway uptime is still needed for its Trust Centre/parent responsibilities.
- `active` means registered/not explicitly departed; it is not an online test. `last_seen` and per-attribute receipt times indicate data age.
- The application registry has 50 lifetime slots, including departed entries; no deletion API exists yet. Its size is independent of Zigbee child/routing tables. The coordinator allows up to 32 direct children; routers must carry additional devices, subject to their own limits.

## Extension points

Extend the existing bounded binding/reporting and SONOFF adapters at the firmware boundary. Preserve per-model capability/acceptance records rather than treating preparation as universal compatibility. Add MQTT or rules on the SBC, using raw stored reports and explicit command-result semantics. Add signed OTA and secured transport before unattended deployment beyond an isolated LAN. Maintain protocol versioning rather than leaking vendor SDK structures into API responses.

## References

- [Espressif board hardware and schematic](https://docs.espressif.com/projects/esp-thread-br/en/latest/hardware_platforms.html)
- [Zigbee gateway reference](https://github.com/espressif/esp-zigbee-sdk/tree/7b9a2e090d5327240a4fad5c2f41da396de05e49/examples/zigbee_gateway)
- [ESP-Zigbee SDK](https://github.com/espressif/esp-zigbee-sdk), ESP-IDF 5.5.4 / Zigbee library 2.0.4 selected for this repository.
