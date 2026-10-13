#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
: "${IDF_PATH:?Source ESP-IDF export.sh first}"
cjson="$IDF_PATH/components/json/cJSON"
test_dir=$(mktemp -d)
trap 'rm -rf -- "$test_dir"' EXIT
cc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I"$root/firmware/main" "$root/tests/firmware_cursor.c" -o "$test_dir/cursor"
"$test_dir/cursor"
cc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I"$root/firmware/main" -I"$cjson" "$root/tests/firmware_json.c" \
  "$cjson/cJSON.c" -lm -o "$test_dir/json"
"$test_dir/json"
echo 'Firmware cursor and JSON tests passed.'
