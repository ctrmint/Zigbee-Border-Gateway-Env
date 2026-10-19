# Repository guidance for coding agents

## Project overview

This repository contains firmware for an ESP32-S3/ESP32-H2 Zigbee gateway and
a Python service/dashboard for a Linux single-board computer. The SBC stores
device configuration and measurement history in SQLite. The dashboard is a
React, Mantine and GridStack application whose built assets are served by the
Python service from `sbc/static/dashboard/`.

Read `README.md`, `CONTRIBUTING.md`, and the relevant guides under `docs/`
before changing behavior. In particular, consult `docs/VALIDATION.md`,
`docs/DEVICE_COMPATIBILITY.md`, and the hardware-specific guide for the device
or feature involved. Keep implemented behavior distinct from planned work and
from hardware acceptance that has not actually been performed.

## Working practices

- Make focused changes on a feature branch. Preserve unrelated user changes and
  never include private local notes such as `AGENT.md` in a commit.
- Treat credentials, device identifiers, household/location names, database
  contents, backups and real-device screenshots as private. Do not print,
  commit, or publish them. Keep `.env`, generated firmware configuration,
  database files, build output and backups out of Git.
- Do not claim hardware behavior based only on simulator or browser tests.
  Report simulator, API, browser, compiler and physical-device evidence
  separately.
- Avoid resetting, flashing, power-cycling, or changing network settings on
  live gateway hardware unless that operation is needed for the requested work.
  A USB serial console can reset the gateway. Prefer read-only inspection for
  operational questions.
- Preserve observed device state. Do not report an actuator state as changed
  until a response or readback confirms it. Keep IEEE addresses as stable
  device identities; names and locations are editable metadata.
- Keep dashboard API changes backward compatible where possible. Version and
  validate contracts, preserve unknown/unrelated saved preferences, and use
  revision/ETag checks for concurrent edits.
- Update user-facing documentation and compatibility/validation records when
  behavior or support claims change. Do not close hardware acceptance items
  without evidence from the physical device.

## Validation commands

Run checks appropriate to the changed component. Do not install dependencies
globally; use a virtual environment for Python development dependencies.

Python service and integration tests:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q sbc tests
python3 -m sbc.contracts --check
```

The contract check assumes the development dependencies in
`requirements-dev.txt` are installed. When changing API contracts, update the
definitions in `sbc/contracts.py` and `sbc/contracts_v2.py`, regenerate the
exported descriptions with `python3 -m sbc.contracts`, and check the generated
files into `docs/api/`.

Dashboard source and production assets:

```sh
cd frontend
npm ci
npm test
npm run build
```

Commit updated production assets and licence notices under
`sbc/static/dashboard/` together with frontend source and lockfile changes.
The Python service does not need Node.js at runtime. Browser tests require the
separately installed Playwright environment:

```sh
python3 -m unittest discover -s tests -p browser_dashboard.py -v
```

For firmware changes, follow `docs/FIRMWARE_SETUP.md` and component-specific
build instructions. Record the exact target and build result; compilation is
not evidence of successful flashing or hardware operation.

## Change completion

Review `git diff` and `git status` before finishing. Keep generated files
intentional and reproducible, avoid unrelated formatting churn, and summarize
what changed plus the checks actually run. Do not commit or publish unless the
user requested that step.
