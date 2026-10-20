# Starlink monitoring

The Starlink dashboard tab displays cached, read-only router diagnostics and
dish satellite-link telemetry. It appears beside System. Router and dish
polling can be enabled independently; neither is required by the Zigbee gateway
or other dashboard tabs.

## What it reads

The router API (`192.168.1.1:9000` by default) provides hardware/software
versions, network prefixes, and client counts for Ethernet, 2.4 GHz, and 5 GHz.
The dish terminal API (`192.168.100.1:9200` by default) can provide link state,
downlink/uplink throughput, point-of-presence ping latency and loss, and
obstruction state/fraction. These are optional terminal-reported fields: a
successful status response can contain only some of them. Missing values remain
unavailable, not zero. In the connected-terminal check recorded below,
throughput and latency were present while state, packet loss, SNR and obstruction
fields were absent. The terminal firmware/model was not captured, so this result
does not establish why each field was omitted or whether another firmware
returns it. The upstream Starlink gRPC tools reference marks SNR obsolete.
Charts show locally collected one-minute samples, retained up to 60 days; the
API returns at most 500 samples from the most recent seven days. Throughput is
actual traffic, not a capacity measurement or speed test.

The service deliberately does not retain device identifiers, client identities,
or dish location. It makes read-only router diagnostics and dish status calls;
it does not call write/control or cloud APIs. Both targets are literal private
IPv4 addresses and configurable. Each gRPC request has a three-second deadline;
polling runs on a worker separate from Zigbee ingestion. A failure on one target
does not change the other target's state. Cached samples are labelled stale
after poll failures or service restarts, and unsupported responses are reported
separately.

## Enable it

Install the optional gRPC and protobuf runtime into the same Python environment
that runs the SBC service. On Raspberry Pi OS, use the distribution packages:

```sh
sudo apt install python3-grpcio python3-protobuf
```

Alternatively, in the service virtual environment install
`requirements-starlink.txt`. Restart the service after installing packages.
Open Configuration & Setup → Starlink. Enable router and/or dish monitoring,
check the corresponding private IPv4 target and gRPC port, then save. The Save
action uses a revision check to avoid overwriting another browser's edits.
Disabling either poller retains that target's configuration and history.

If the optional runtime is absent, the dashboard reports that dependency status;
the base service remains operational. A connection refused, deadline expiry or
unsupported method appears in the status with the last successful sample retained
when one exists. This feature does not change Starlink settings or expose its
APIs to the browser.

## Data and API

The authenticated SBC endpoints are `GET /api/v2/starlink`,
`GET /api/v2/starlink/config`, and revision-checked `PUT
/api/v2/starlink/config`. The dashboard reads only the SBC API. Configuration is
shared across browser profiles. Summary history is stored in SQLite, retained
for at most 60 days, and the current API response includes up to 500 samples
from the last seven days. System-dashboard data purge also removes older
Starlink samples.

The router endpoint and `GetDiagnostics` call follow SpaceX's public [Local
Device API README](https://github.com/SpaceExplorationTechnologies/enterprise-api/blob/master/device-api/README.md)
and [device protobuf schema](https://github.com/SpaceExplorationTechnologies/enterprise-api/blob/master/device-api/device.proto).
Dish status field numbers and meanings use the publicly available [dish schema
subset](https://docs.rs/crate/starlink/latest/source/proto/spacex/api/device/dish.proto)
and [Starlink gRPC tools reference](https://github.com/sparky8512/starlink-grpc-tools).
Dish status telemetry is not part of the current minimal SpaceX-published proto
subset and can vary by terminal firmware. A field appearing in a community
schema does not guarantee that the terminal supplies it; absence is represented
as unavailable, not zero.

## Validation boundary

Automated tests use a local fake gRPC service and verify router and dish request
methods, response decoding, bounds, authentication, configuration conflicts,
disabled behavior, independent stale handling, and retention. On 20 October
2026, the connected Pi saved the dish target and received an `available` status
from the terminal. A live sample contained downlink and uplink throughput and
PoP latency; the other listed metrics were absent in that response. The check
confirms the endpoint and these returned values only. It does not verify the
accuracy or completeness of optional fields across firmware versions. Browser
automation and physical iPad acceptance for this new tab were not run.
