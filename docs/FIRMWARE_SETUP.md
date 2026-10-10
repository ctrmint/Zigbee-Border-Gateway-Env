# Firmware build and flashing

## Selected baseline

- ESP-IDF **v5.5.4**.
- ESP-Zigbee library **2.0.4**, exact version in `main/idf_component.yml`.
- S3/H2 gateway reference snapshot `7b9a2e090d5327240a4fad5c2f41da396de05e49`.
- H2 runs IDF `ot_rcp` with the vendor hook enabled; S3 runs our Zigbee coordinator application. The RCP's OpenThread name does not mean this application creates a Thread network.

Install Git, Python, CMake, Ninja and ESP-IDF's documented OS prerequisites. On Fedora use the [Espressif Linux installation guide](https://docs.espressif.com/projects/esp-idf/en/v5.5.4/esp32s3/get-started/linux-macos-setup.html); ensure your user has access to the USB serial/JTAG devices.

```bash
git clone --branch v5.5.4 --recursive https://github.com/espressif/esp-idf.git
cd esp-idf
./install.sh esp32s3,esp32h2
. ./export.sh
cd ../zigbee-border-gateway
```

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
