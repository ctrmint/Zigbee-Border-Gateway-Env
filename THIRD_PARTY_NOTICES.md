# Third-party notices

`firmware/main/zigbee_gateway.c`, `zigbee_gateway.h`, `zigbee_rcp.c`, `zigbee_rcp.h`, the base Kconfig, partition/default configuration and `firmware/components/example_common` derive from Espressif's gateway examples at commit `7b9a2e090d5327240a4fad5c2f41da396de05e49` (retrieved 2026-10-10). Their original public-domain/CC0 declarations and copyright/SPDX notices are retained. Modifications add this project's API and commissioning policy.

ESP-IDF, ESP-Zigbee library, RCP update components and their dependencies retain their respective licenses; they are fetched at build time, not relicensed by this repository. The Zigbee stack includes Espressif proprietary prebuilt libraries. See upstream licenses before redistribution or commercial use. No prebuilt vendor binaries are included in the archive.

## Starlink local Device API schema subset

`sbc/starlink_device.proto` and its generated Python message module implement
read-only router `GetDiagnostics` and dish `GetStatus` field subsets. Router
field numbers and service/package name follow Space Exploration Technologies'
published [Local Device API](https://github.com/SpaceExplorationTechnologies/enterprise-api/tree/master/device-api).
Dish status field numbers are based on the public [dish schema subset](https://docs.rs/crate/starlink/latest/source/proto/spacex/api/device/dish.proto),
also used by the [Starlink gRPC tools reference](https://github.com/sparky8512/starlink-grpc-tools).
This repository does not include Starlink's full schema or generated API
implementation. The dish status interface is firmware-dependent and is not
specified by the currently published SpaceX proto. Upstream APIs and device
firmware remain subject to their own terms and compatibility limits.

`firmware/rcp/main` and the RCP build/default/partition files derive from ESP-IDF v5.5.4 `examples/openthread/ot_rcp` (commit `735507283d5b2f9fb363a1901172dbd9e847945d`), under retained CC0/public-domain notices. Optional console and coexistence helpers are omitted in this minimal source.

## Dashboard migration frontend

The React/Mantine/GridStack dashboard uses packages pinned in
`frontend/package-lock.json`. The production build emits their installed licence
texts in `sbc/static/dashboard/assets/third-party-licenses.txt`. See
[dashboard migration](docs/DASHBOARD_MIGRATION.md) for build/runtime scope.
