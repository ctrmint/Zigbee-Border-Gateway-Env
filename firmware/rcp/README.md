# ESP32-H2 RCP

Build with ESP-IDF v5.5.4: `idf.py -C firmware/rcp set-target esp32h2 build`. Flash using USB1/H2. Source derives from the IDF `ot_rcp` example; optional diagnostic and external coexistence helpers are removed for this minimal radio build. RX23/TX24 and Zigbee-compatible vendor hooks are selected in defaults. See [firmware setup](../../docs/FIRMWARE_SETUP.md).
