# Roadmap

## First hardware milestone

Validate the compiled S3 and H2 source on the delivered board revision, then pair one standard plug and one standard sensor. Record manufacturer/model, endpoint map, pairing sequence and any configuration requirements. Perform restart, short-address-change and interference tests before increasing device count.

## Next implementation work

1. Add IEEE-addressed binding and Configure Reporting to the firmware API, with bounded interview queues, callbacks, timeouts and retry policies for sleepy devices. Read manufacturer/model automatically.
2. Track command IDs, APS confirmations and ZCL transaction IDs. Add controlled read-back where appropriate, without equating send acceptance with actuator confirmation.
3. Add tested device adapters, IAS Zone enrolment and metering scale factors. Preserve raw data alongside normalized values.
4. Add authenticated encrypted transport to the board, signed firmware updates and tested secure storage. Support credential rotation without wiping network state.
5. Add MQTT publishing and a rule engine on the SBC. Make rules opt-in, validate stale data, and define offline and fail-safe behaviours before actuator integration.
6. Implement documented IEEE registry deletion, state schema migrations and secure network backup/recovery with frame-counter handling.
7. Benchmark 20–50 nodes, router distribution, RF coexistence, memory, event buffering and discovery concurrency. Enable Ethernet/PTA only with tested matching board configuration.

The current release contains source for the coordinator/API and SBC dashboard/history MVP. It does not promise these planned features or universal device compatibility.
