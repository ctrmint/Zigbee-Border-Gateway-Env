# Contributing

Run `python3 -m unittest discover -s tests -v` and build S3 firmware before submitting changes. Keep API schemas versioned, preserve IEEE identity, avoid optimistic actuator state and never log credentials. Add manufacturer/model evidence and hardware logs for new compatibility claims. Each source change should state simulator, compiler and hardware validation separately.

Install test dependencies from `requirements-dev.txt` in a virtual environment.
When changing an API, update the applicable definitions in `sbc/contracts.py` and `sbc/contracts_v2.py`, regenerate descriptions with
`python3 -m sbc.contracts`, and run `python3 -m sbc.contracts --check`. Keep planned
routes in `docs/DASHBOARD_API_DESIGN.md` distinct from implemented contracts.
