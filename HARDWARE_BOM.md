# Hardware bill of materials

For a 20–50 device home deployment. Purchase references identify products; pricing and availability have not been quoted. Verify the delivered board revision and schematic before flashing.

| Item | Qty | Selection / purpose | Reference |
| --- | --- | --- | --- |
| Espressif ESP Thread Border Router / Zigbee Gateway | 1 | **ESP32-S3 + ESP32-H2** main board, ordering family ESP32-S3-Thread-BR; not an H2 DevKit alone | [Espressif board and ordering](https://docs.espressif.com/projects/esp-thread-br/en/latest/hardware_platforms.html#ordering) |
| USB Type-C data cable | 1–2 | Flash either SoC; two cables useful for concurrent logs | [Pi Hut cables](https://thepihut.com/collections/usb-cables) |
| Regulated USB 5 V power supply | 1 | Quality USB supply, at least 1 A capacity for main-board development; use board vendor guidance for accessories | [Pi Hut power supplies](https://thepihut.com/collections/raspberry-pi-power-supplies) |
| Linux SBC | 1 | Raspberry Pi 4 with 2 GB+ RAM is ample for this service; Pi 5 or an existing Linux server also works | [Raspberry Pi 4](https://www.raspberrypi.com/products/raspberry-pi-4-model-b/) |
| SBC power supply | 1 | Match chosen Pi model; use its official supply | [Raspberry Pi accessories](https://www.raspberrypi.com/products/) |
| SBC storage | 1 | 32 GB+ high-endurance microSD or USB SSD; SSD preferred for continuous history writes | [Pi Hut storage](https://thepihut.com/collections/raspberry-pi-sd-cards) |
| Ethernet cable | 1 | SBC to router, leaving Wi-Fi for gateway | [Pi Hut networking](https://thepihut.com/collections/raspberry-pi-networking) |
| Zigbee mains-powered routing plugs | 2–3 initially | Choose UK-rated genuine Zigbee devices with standard On/Off cluster; verify routing and compatibility | Existing devices can be used; check manufacturer model before purchase |
| Zigbee temperature/humidity sensor | 1 initially | Standard 0x0402/0x0405 clusters preferred, no Tuya-only data-point device for first test | Check endpoint/cluster documentation for selected model |
| Non-metal enclosure and standoffs | 1 set | Keep antennas unobstructed; allow service access to both USB ports/buttons | Print after measuring the actual revision |
| Optional Sub-Ethernet daughter board | 1 | Matching Espressif W5500 add-on; requires firmware driver/configuration work | [Espressif hardware reference](https://docs.espressif.com/projects/esp-thread-br/en/latest/hardware_platforms.html) |

## What to buy first

Buy the S3/H2 gateway main board, a data cable and one known standard Zigbee sensor or plug. Reuse your Linux machine for the SBC service while validating. Add the dedicated SBC and routing devices once pairing/control work.

## Power and ports

Board documentation identifies **USB1 = H2**, **USB2 = S3**, each USB-C. Either powers the main board. Confirm the board silkscreen and the enumerated chip when choosing ports; Linux device numbering is not stable. In normal service, power through USB2. The board is not a PoE device.

The board provides separate Wi-Fi and 802.15.4 radios, not immunity from 2.4 GHz interference. Place it away from APs, metalwork and USB3 storage. Zigbee channel 20 is the starting configuration, not a universally optimal selection.
