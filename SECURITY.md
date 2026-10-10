# Security notes

The MVP uses independent bearer tokens for the SBC and gateway, explicit brief join windows, local binding by default, strict SBC command schemas and no automatic actuator retries. Tokens must be 32+ characters; use `secrets.token_hex(32)`. Firmware accepts tokens up to 120 characters. Generated `sdkconfig` embeds the gateway token and Wi-Fi credentials, so it is ignored by Git.

**Transport is plain HTTP in this release.** Tokens and commands can be observed by a network attacker. Use a private isolated network, restrict board port 80 to the SBC, and keep the dashboard on localhost or behind an authenticated HTTPS reverse proxy/VPN. A reverse proxy protects browser-to-SBC traffic; it does not encrypt SBC-to-board traffic. Board TLS, secure boot, flash/NVS encryption and signed OTA require further implementation and key management.

Firmware is based on the vendor's default centralized coordinator policy with distributed security disabled and install-code policy false. It does not implement install-code onboarding, per-device allowlists, rate limiting, account-level authorization or audited credential rotation. Pair one device at a time and close joining immediately afterwards.

The supplied SBC HTTP server is a small development service. For wider or unattended exposure, replace/harden the serving layer and add transport security, request/concurrency limits and stronger authorization. Do not expose it or the board through router port forwarding.

Browser tokens are kept in page memory only, not local storage or URLs. Device metadata renders through `textContent` to avoid HTML injection. Logs intentionally omit tokens and request URLs. Protect `.env`, firmware images, NVS and SQLite backups.

Report vulnerabilities privately to the repository owner before opening public issues containing secrets. There is no external reporting address configured in this initial repository.
