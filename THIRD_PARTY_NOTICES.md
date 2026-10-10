# Third-party notices

`firmware/main/zigbee_gateway.c`, `zigbee_gateway.h`, `zigbee_rcp.c`, `zigbee_rcp.h`, the base Kconfig, partition/default configuration and `firmware/components/example_common` derive from Espressif's gateway examples at commit `7b9a2e090d5327240a4fad5c2f41da396de05e49` (retrieved 2026-10-10). Their original public-domain/CC0 declarations and copyright/SPDX notices are retained. Modifications add this project's API and commissioning policy.

ESP-IDF, ESP-Zigbee library, RCP update components and their dependencies retain their respective licenses; they are fetched at build time, not relicensed by this repository. The Zigbee stack includes Espressif proprietary prebuilt libraries. See upstream licenses before redistribution or commercial use. No prebuilt vendor binaries are included in the archive.

`firmware/rcp/main` and the RCP build/default/partition files derive from ESP-IDF v5.5.4 `examples/openthread/ot_rcp` (commit `735507283d5b2f9fb363a1901172dbd9e847945d`), under retained CC0/public-domain notices. Optional console and coexistence helpers are omitted in this minimal source.
