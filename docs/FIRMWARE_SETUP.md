# Firmware build and flashing

## Selected baseline

- ESP-IDF **v5.5.4**.
- ESP-Zigbee library **2.0.4**, exact version in `main/idf_component.yml`.
- S3/H2 gateway reference snapshot `7b9a2e090d5327240a4fad5c2f41da396de05e49`.
- H2 runs IDF `ot_rcp` with the vendor hook enabled; S3 runs our Zigbee coordinator application. The RCP's OpenThread name does not mean this application creates a Thread network.

The Raspberry Pi is both the dashboard server and the firmware development
workstation. Build, flash and monitor over an SSH login on the Pi; the USB cable
connects the ESP board directly to the Pi. The deployed SBC service communicates
with the S3 API over the LAN.

Install Git, Python, CMake, Ninja and ESP-IDF's documented OS prerequisites using
the [Espressif Linux installation guide](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32s3/get-started/linux-macos-setup.html).
Ensure your user has access to the USB serial/JTAG devices (`dialout` on Raspberry
Pi OS; log out and back in after changing group membership).

```bash
git clone --branch v5.5.4 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh esp32s3,esp32h2
. ./export.sh
cd ../zigbee-border-gateway
```

On this Pi, the toolchain checkout is `/home/mark/esp/esp-idf` and the project is
`/home/mark/Zigbee-Border-Gateway-Env`. For a new SSH terminal:

```bash
. /home/mark/esp/esp-idf/export.sh
cd /home/mark/Zigbee-Border-Gateway-Env
```

## Identify the connected chip

```bash
ls -l /dev/serial/by-id/
python -m esptool --port /dev/ttyACM0 chip-id
```

Use the actual persistent `/dev/serial/by-id/...` path where available. A USB
manufacturer string alone does not identify the S3 or H2. Verify the chip with
esptool before choosing the firmware image. If the port opens but no serial
response arrives, confirm the board connector and enter download mode: hold
BOOT, press and release RESET, then release BOOT. Repeat identification after
checking the port again. Do not flash until chip identification succeeds.

If developing with a sandboxed agent, its environment must also permit serial
device access; working serial permissions in the SSH shell do not ensure that
the agent sees the device.

## 1. Build/flash H2 radio

```bash
cd firmware/rcp
idf.py set-target esp32h2
idf.py build
idf.py -p /dev/ttyACM_H2 flash
cd ../..
```

Replace the illustrative serial port with the actual port for **USB1 / H2**. Do not guess from enumeration order. The included RCP source derives from the pinned IDF example with optional diagnostics/coexistence helpers removed. Board defaults are: RX23, TX24, UART 460800 baud and `OPENTHREAD_NCP_VENDOR_HOOK=y`. Check generated `sdkconfig` and preserve a tested RCP image for later recovery.

## 2. Configure/build/flash S3

```bash
cd firmware
idf.py set-target esp32s3
idf.py menuconfig
```

Configure:

- `Example Connection Configuration`: your 2.4 GHz Wi-Fi SSID/password.
- `Local gateway API`: a unique token generated using `secrets.token_hex(32)`.
- Zigbee primary channel: default 20; choose after checking local Wi-Fi occupancy.
- Confirm UART-RCP mode, coordinator/router build and pins RX17/TX18.
- Confirm USB Serial/JTAG console output for development through USB2.
- Leave automatic RCP update **disabled**; direct H2 flashing is used here.

```bash
idf.py build
idf.py -p /dev/ttyACM_S3 flash monitor
```

Use **USB2 / S3**. Monitor should show network connection and successful Zigbee formation/restoration. Note the S3 IP, assign a DHCP reservation, then call `/api/v1/health` with your gateway token.

The conservative reference partition layout uses the first 4 MB and does not enable PSRAM or OTA. The board may provide additional flash/PSRAM; those are not required for this MVP. Do not select a larger partition layout without confirming the exact module. `nvs` stores network state; do not erase it on each build.

## VS Code

Open the repository and use the Espressif ESP-IDF extension. Select `firmware/` as the project directory, ESP32-S3 as target and the S3 port. H2 is a separate build in `firmware/rcp`. Normal CMake configuration resolves ESP Registry dependencies. This repository is an ESP-IDF project, not an Arduino sketch.

## Troubleshooting

| Symptom | Checks |
| --- | --- |
| Boot fails immediately with invalid argument | Configure the API token (32–120 characters) |
| RCP handshake failure | H2 correct image/vendor hook, UART pins/baud, board powered, correct USB chip flashed |
| Host will not associate | 2.4 GHz SSID, password, DHCP, Wi-Fi signal |
| Device joins but no measurements | Wake device, inspect endpoints, read attributes; reporting/binding is not configured automatically |
| Empty descriptors | Keep sleepy device awake, use Discover again, review compatibility |
| API 401 | Token matches firmware; do not confuse dashboard token with board token |
| API 503 | Stack not formed/restored, busy or SDK rejected the command; inspect serial log |

A factory reset/`erase-flash` is deliberately not part of the normal workflow. It discards the network and may require re-pairing all devices.

## Firmware regression checks

After exporting ESP-IDF, run the native C tests on the Pi:

```bash
bash scripts/test_firmware_host.sh
```

These use the pinned IDF cJSON source and exercise command-body parsing, duplicate
fields, embedded NULs, malformed cursors, ring gaps and cursor arithmetic at
`UINT32_MAX`. Both firmware targets must additionally build; native tests do not
exercise the Zigbee stack or prove radio delivery. Leave the API token blank for
compile-only validation, then configure real credentials locally before a
deployable build. Generated `sdkconfig` and build artifacts are Git-ignored.
