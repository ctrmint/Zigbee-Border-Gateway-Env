# Continuous gateway Wi-Fi recovery (#28)

The S3 uses an application-owned network worker instead of the example helper's finite retry loop. AP absence at boot or after disconnect does not block Zigbee startup or exhaust a lifetime retry budget. Connection operations have 25-second deadlines and increasing delays capped at 31 seconds including jitter. Backoff resets after ten seconds of stable IP connectivity. There is no attempt-count exit, even after prolonged failure.

The worker checks actual association/IP state rather than trusting callback ordering. Duplicate disconnect notifications cannot repeatedly fail one attempt; stale got-IP callbacks cannot declare a disconnected link healthy. Missing IP configuration triggers DHCP renewal, then reassociation after repeated unsuccessful renewals. Wi-Fi interface restart is reserved for repeated driver/API errors with a two-minute cooldown; ordinary missing-AP responses do not trigger reboot cycles.

HTTP startup and repair belong to the worker once link/IP are ready. Local health probes check the authenticated API every 30 seconds, with listener repair after three failures. An independent progress watchdog detects a worker that stops making progress for 20 seconds. Controlled recovery reboots preserve network storage, and repeated recovery faults have a 15-minute reboot guard retained in RTC no-init memory. Five minutes of healthy network/API operation clears the guard. The watchdog monitors task progress, not AP availability: a responsive worker must keep retrying through an overnight outage without rebooting merely because the network is absent.

Network recovery never erases flash, resets the Zigbee network or deliberately switches a plug/load. Individual operation failures, initial hardware/driver initialization failures, unavailable APs and invalid credentials must remain distinguishable. Software cannot repair failed hardware, absent power or permanently wrong credentials; the recovery loop continues rather than claiming it can manufacture connectivity under those conditions.

## Discovery and Pi recovery

The authenticated health response exposes a stable `gateway_id` (S3 Wi-Fi MAC without separators) and `network` diagnostics. After an initial successful authenticated connection, the Pi pins that identity to its configured URL/token fingerprint in SQLite `gateway_bindings`. The last verified endpoint is retained across Pi restarts. An address change does not require editing `.env`.

On transport failure, the Pi can send a nonce challenge on UDP port **39128** using global/local-subnet broadcast, at most once every 30 seconds with a 1.5-second response window. Request proof is HMAC-SHA256 of `discover|nonce` with the existing gateway token; the firmware verifies it before responding. Response proof binds nonce, gateway identity and port. Tokens are never placed in discovery packets. The client accepts only its pinned identity and valid proof, then authenticates HTTP health at that endpoint before using it. Ordinary HTTP errors are not blindly treated as transport failures; a previously pinned address returning another identity/401/404 can trigger rediscovery.

Read requests may resume after a verified endpoint change. An uncertain write is never automatically replayed: it may already have executed. Callers retain their existing device acknowledgement/readback logic.

This requires the Pi and gateway to have usable LAN connectivity and allow the discovery traffic. A DHCP reservation is optional operational support, not the sole recovery mechanism. Initial commissioning still requires a known authenticated address to pin the intended identity; replacing the board or deliberately changing credentials requires updating that configuration. Reusing one token across unrelated gateways defeats identity bootstrap assumptions.

The Pi keeps retrying throughout an outage. Its connected status becomes true only after successful authenticated polling, not merely a discovery reply. Retained events are drained after reconnection; finite gateway ring-buffer limits still apply. Restart/overflow/unavailable periods are recorded as history gaps rather than fabricated samples. Existing reports are shown with their ages while offline. Buffered event ages are reconstructed from authenticated same-boot gateway uptime, so a recovered old measurement does not become fresh merely because it just reached the Pi. Raw event receipt time remains recorded separately; `observed_at_estimate` labels the inferred gateway receipt time. History, sensor values and RSSI use that estimate when available, with ordinary polling/transport uncertainty; older records without source uptime retain Pi receipt semantics.

## Diagnostics

Open **Configuration & Setup → Wi-Fi recovery diagnostics**. The response timestamp and an explicit cached/offline label distinguish old diagnostics from a current authenticated response. New firmware reports association/IP/API state, IPv4 address, Wi-Fi RSSI, attempts/consecutive failures, next attempt and last connection times, last disconnect reason, driver/listener restart counts, event drops, driver errors, reset/recovery-reboot reason and progress timestamp. Millisecond fields refer to gateway uptime, not UTC. Unknown Wi-Fi RSSI is null. This Wi-Fi signal is separate from each Zigbee sensor's received RSSI.

Two compact NVS counters retain the previous checkpoint's disconnect reason and attempt count. Checkpoint writes are limited to the first incident per boot and at most once per hour afterward; normal successful polling and unchanged endpoint bindings do not rewrite flash. Recovery-reboot guard limits repeated fault reboots; external power cycling can of course cause additional boots. Wi-Fi passwords and bearer tokens are not included in diagnostics.

Authenticated discovery also reports limited network/API/uptime diagnostics so an HTTP listener outage can be investigated without using a reset as a diagnostic method. The response proof authenticates the identity/port selection; these auxiliary fields are diagnostic information, not inputs that authorize device writes.

## Deployment and rollback

Back up the configured Pi database/source and full S3 flash before deployment. Build with the existing private credentials, compare partition tables and flash only the factory application. Preserve bootloader, NVS, partition table, Zigbee storage and H2 firmware. Restart the Pi service to load the new client and binding table. Store full images/configuration backups privately: they contain credentials.

If rollback is necessary, retain newer history and restore compatible source/application/configuration without erasing network storage. The additional Pi binding table is additive; it does not alter profiles, layouts or sensor history. Any deployment boot must be recorded separately from autonomous recovery proof.

## Bounded validation hook

`CONFIG_GW_NETWORK_TEST` defaults **off**. A validation build can enable authenticated `POST /api/v1/network-test` with exactly `{"seconds": 180}` (range 1–300). The worker temporarily selects an unavailable SSID in RAM, continues normal recovery attempts, and autonomously restores the original configuration at expiry. It does not modify stored credentials, reset Zigbee or reboot as the means of restoring the network. Concurrent tests are rejected. There is no dashboard control that invokes this endpoint.

Record the pre/post boot ID, attempt/failure counts, offline duration, API availability, Pi reconnection, network/registry preservation and recording gaps. Do not use a manual reset, serial-control toggle or separate Wi-Fi restart to make an outage test pass. A simulated unavailable SSID is not evidence that an actual router reboot, changed DHCP lease or overnight outage was tested; record each separately.

USB console handling matters on this board. Pyserial can toggle DTR and RTS separately while opening a port and cause a reset. A raw Linux CDC-ACM read with no modem-control/termios changes was verified with uninterrupted discovery responses; any console inspection must still be distinguished from firmware recovery. Relevant primary references: [ESP32-S3 reset controls](https://docs.espressif.com/projects/esptool/en/latest/esp32s3/advanced-topics/boot-mode-selection.html) and [Linux CDC-ACM combined control handling](https://github.com/torvalds/linux/blob/v6.12/drivers/usb/class/cdc-acm.c#L623).

The operational acceptance target is authenticated API/Pi reconnection within 180 seconds after a usable AP and DHCP service return under normal network conditions. The bounded live test returned in about 2.2 seconds after its 180-second injected outage; this does not establish the worst case for actual router restarts or changed leases.

See [validation results](VALIDATION.md) and issue #28 for exact tested images and outstanding hardware scenarios. Do not close extended hardware acceptance solely on compilation or synthetic time progression.

## Subsequent Pi/Starlink interruption: scope of evidence

On 18 October, Pi Wi-Fi/router/DNS/internet access, the dashboard and gateway were reachable after the user manually power-cycled the Pi to recover lost access. Gateway/plug reporting resumed and registrations were preserved. This is a recovery observation after a manual reboot; it does **not** establish whether the original failure was Pi Wi-Fi, upstream Starlink/router connectivity or a Pi lockup. The previous-boot Pi journal used volatile storage and was unavailable. A later clean connection or power-on reset code does not reconstruct that cause.

The previously documented 180-second same-boot worker test remains the autonomous gateway Wi-Fi evidence. Extended overnight/repeated outages, real DHCP-address change, AP/router restart without a manual gateway reset and forced internal-stall escalation remain open in #28. See [Pi incident logging](OPERATIONS.md#pi-access-loss-and-persistent-incident-logs) for a bounded optional administrator setup to preserve future evidence, and [hardware validation](HARDWARE_VALIDATION_2026-10-18.md) for observed plug/coordinator restart behavior. No logging/network setting was changed as part of this documentation update.
