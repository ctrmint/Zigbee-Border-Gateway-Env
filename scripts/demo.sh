#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -f .env ]]; then
  echo 'Copy .env.example to .env and configure two random tokens first.' >&2
  exit 1
fi
set -a
source .env
set +a
export GATEWAY_URL=http://127.0.0.1:8081
export SIM_PORT=8081
export DB_PATH=data/demo.sqlite3
python3 -m sbc.simulator &
sim_pid=$!
trap 'kill "$sim_pid" 2>/dev/null || true' EXIT
python3 -m sbc.app
