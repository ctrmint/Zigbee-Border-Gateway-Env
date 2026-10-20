import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Paper,
  Select,
  SimpleGrid,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { Activity, Network, Radio, RefreshCw, Route } from "lucide-react";

function Metric({ label, value, detail }) {
  return (
    <Card withBorder padding="md" className="radio-metric">
      <Text size="xs" c="dimmed">
        {label}
      </Text>
      <Text fw={700} size="lg">
        {value ?? "Unavailable"}
      </Text>
      {detail && (
        <Text size="xs" c="dimmed">
          {detail}
        </Text>
      )}
    </Card>
  );
}

function shortAddress(value) {
  return Number.isInteger(value)
    ? `0x${value.toString(16).padStart(4, "0")}`
    : "Unknown";
}

function SignalChart({ history }) {
  const points = (history?.items || []).filter(
    (item) => item.quality === "valid" && Number.isFinite(item.value),
  );
  if (points.length < 2)
    return (
      <Text c="dimmed" size="sm">
        Not enough valid signal samples to draw a trend.
      </Text>
    );
  const values = points.map((point) => point.value),
    min = Math.min(...values),
    max = Math.max(...values);
  const span = max - min || 1;
  const y = (point) => 90 - ((point.value - min) / span) * 72;
  const segments = [];
  let segment = [];
  points.forEach((point, i) => {
    if (
      i &&
      (history?.gaps || []).some(
        (gap) =>
          points[i - 1].received_at < gap.to && point.received_at > gap.from,
      )
    ) {
      if (segment.length > 1) segments.push(segment);
      segment = [];
    }
    segment.push(`${(i * 300) / (points.length - 1)},${y(point)}`);
  });
  if (segment.length > 1) segments.push(segment);
  return (
    <>
      <svg
        className="radio-signal-chart"
        viewBox="0 0 300 100"
        role="img"
        aria-label={`Coordinator reception signal history, ${points.length} samples from ${min} to ${max} dBm`}
      >
        <line x1="0" y1="90" x2="300" y2="90" className="radio-chart-axis" />
        {segments.map((coords, i) => (
          <polyline
            key={i}
            points={coords.join(" ")}
            fill="none"
            className="radio-chart-line"
          />
        ))}
      </svg>
      <Group justify="space-between">
        <Text size="xs" c="dimmed">
          {new Date(points[0].received_at * 1000).toLocaleString()}
        </Text>
        <Text size="xs" c="dimmed">
          {new Date(points.at(-1).received_at * 1000).toLocaleString()}
        </Text>
      </Group>
      <Text size="xs" c="dimmed" mt={4}>
        Reception at the coordinator, from passive event history; it does not
        identify the route.
        {history?.gaps?.length
          ? ` The line is broken for ${history.gaps.length} recorded ingestion gap${history.gaps.length === 1 ? "" : "s"}.`
          : ""}
      </Text>
    </>
  );
}

export default function RadioDashboard({ api }) {
  const [snapshot, setSnapshot] = useState(null),
    [devices, setDevices] = useState([]);
  const [selected, setSelected] = useState(null),
    [history, setHistory] = useState(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const refresh = useCallback(
    async (signal) => {
      setBusy(true);
      try {
        const [radio, inventory] = await Promise.all([
          api.request("/api/v2/radio", { signal }),
          api.request("/api/v2/devices", { signal }),
        ]);
        setSnapshot(radio.data);
        setDevices(inventory.data.devices || []);
        setSelected(
          (current) => current || inventory.data.devices?.[0]?.ieee || null,
        );
        setError("");
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
      } finally {
        setBusy(false);
      }
    },
    [api],
  );
  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    const id = setInterval(() => refresh(), 30000);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, [refresh]);
  useEffect(() => {
    if (!selected) {
      setHistory(null);
      return;
    }
    const controller = new AbortController(),
      to = Date.now() / 1000;
    const params = new URLSearchParams({
      ieee: selected,
      endpoint: "1",
      cluster: "65535",
      attribute: "0",
      from: String(to - 86400),
      to: String(to),
      limit: "500",
    });
    api
      .request("/api/v2/history?" + params, { signal: controller.signal })
      .then((result) => setHistory(result.data))
      .catch((e) => {
        if (e.name !== "AbortError") setHistory({ error: e.message });
      });
    return () => controller.abort();
  }, [api, selected]);
  const neighborNames = useMemo(
    () => new Map(devices.map((device) => [device.ieee, device.name])),
    [devices],
  );
  const selectedDevice = devices.find((device) => device.ieee === selected);
  const mode =
    snapshot?.mode === "simulator" ? "Simulator data" : "Coordinator snapshot";
  const age = snapshot?.observed_at
    ? Math.max(0, Math.floor(Date.now() / 1000 - snapshot.observed_at))
    : null;
  const latestRssi = selectedDevice?.signal?.value;

  return (
    <section className="radio-dashboard" aria-label="Radio dashboard">
      <Group justify="space-between" align="flex-end" mb="lg">
        <div>
          <Text className="eyebrow">ZIGBEE MESH HEALTH</Text>
          <Title order={2}>Radio</Title>
          <Text c="dimmed" size="sm">
            Passive coordinator metrics and recorded signal performance. Viewing
            this page sends no Zigbee network requests to devices.
          </Text>
        </div>
        <Button
          variant="light"
          leftSection={<RefreshCw size={16} />}
          onClick={() => refresh()}
          loading={busy}
        >
          Refresh
        </Button>
      </Group>
      {error && (
        <Alert color="red" mb="md" title="Radio information refresh failed">
          {error}{" "}
          {snapshot?.status === "available"
            ? "Showing the last received snapshot."
            : ""}
        </Alert>
      )}
      {snapshot?.status === "unsupported" && (
        <Alert color="orange" mb="md" title="Gateway firmware update required">
          This gateway firmware does not expose coordinator radio tables.
          Recorded RSSI history remains available below.
        </Alert>
      )}
      {snapshot?.status === "unavailable" && (
        <Alert color="orange" mb="md" title="Radio snapshot unavailable">
          The coordinator has not returned a local radio snapshot yet.
        </Alert>
      )}
      {snapshot?.status === "stale" && (
        <Alert color="orange" mb="md" title="Showing a stale radio snapshot">
          The latest refresh failed. Last successful snapshot is shown with its
          age.
        </Alert>
      )}

      <SimpleGrid cols={{ base: 1, xs: 2, md: 3, xl: 6 }} mb="xl">
        <Metric
          label="Network"
          value={snapshot?.ready ? "Coordinator ready" : "Unavailable"}
          detail={`${mode}${age == null ? "" : ` · snapshot ${age}s ago`}`}
        />
        <Metric
          label="Channel"
          value={snapshot?.channel ?? "Unavailable"}
          detail="Zigbee channel"
        />
        <Metric
          label="PAN ID"
          value={
            snapshot?.pan_id == null
              ? "Unavailable"
              : `0x${snapshot.pan_id.toString(16).padStart(4, "0")}`
          }
          detail="Current network identifier"
        />
        <Metric
          label="Gateway uptime"
          value={
            snapshot?.uptime_ms == null
              ? "Unavailable"
              : `${Math.floor(snapshot.uptime_ms / 3600000)}h ${Math.floor(snapshot.uptime_ms / 60000) % 60}m`
          }
          detail="Since last gateway boot"
        />
        <Metric
          label="Coordinator neighbors"
          value={snapshot?.neighbors?.length ?? "Unavailable"}
          detail="Direct entries in the coordinator neighbor table"
        />
        <Metric
          label="Routes / source routes"
          value={
            snapshot
              ? `${snapshot.routes?.length ?? 0} / ${snapshot.route_records?.length ?? 0}`
              : "Unavailable"
          }
          detail="Coordinator-local tables; not a complete network map"
        />
      </SimpleGrid>
      <SimpleGrid cols={{ base: 1, xs: 2 }} mb="xl">
        <Metric
          label="Gateway event drops"
          value={snapshot?.dropped_events ?? "Not exposed"}
          detail={`Latest event sequence ${snapshot?.latest_seq ?? "unavailable"}`}
        />
        <Metric
          label="Snapshot source"
          value={snapshot?.neighbor_source || "Unavailable"}
          detail="Aging and role fields are supplied by the coordinator neighbor table."
        />
      </SimpleGrid>

      <Paper withBorder p="md" mb="xl">
        <Group mb="sm">
          <Network size={18} />
          <Title order={3}>Coordinator links</Title>
          <Badge variant="light">
            {snapshot?.scope || "Waiting for snapshot"}
          </Badge>
        </Group>
        <Text size="sm" c="dimmed" mb="md">
          Neighbor entries describe links known by the coordinator only. Other
          routers’ neighbor tables are not queried, and RSSI is not used to
          infer a route.
        </Text>
        {snapshot?.neighbors?.length ? (
          <Table.ScrollContainer minWidth={1120}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Device</Table.Th>
                  <Table.Th>Role</Table.Th>
                  <Table.Th>Relationship</Table.Th>
                  <Table.Th>LQI</Table.Th>
                  <Table.Th>RSSI</Table.Th>
                  <Table.Th>Outgoing cost</Table.Th>
                  <Table.Th>Depth / age</Table.Th>
                  <Table.Th>Rx idle</Table.Th>
                  <Table.Th>Device timeout</Table.Th>
                  <Table.Th>Timeout counter</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {snapshot.neighbors.map((neighbor) => (
                  <Table.Tr key={neighbor.ieee || neighbor.nwk}>
                    <Table.Td>
                      {neighborNames.get(neighbor.ieee) ||
                        neighbor.ieee ||
                        shortAddress(neighbor.nwk)}
                    </Table.Td>
                    <Table.Td>
                      {["Coordinator", "Router", "End device"][
                        neighbor.device_type
                      ] || `Type ${neighbor.device_type ?? "unknown"}`}
                    </Table.Td>
                    <Table.Td>
                      {["Parent", "Child", "Sibling", "Other"][
                        neighbor.relationship
                      ] || "Unknown"}
                    </Table.Td>
                    <Table.Td>{neighbor.lqi ?? "Unavailable"}</Table.Td>
                    <Table.Td>
                      {neighbor.rssi_dbm == null
                        ? "Unavailable"
                        : `${neighbor.rssi_dbm} dBm`}
                    </Table.Td>
                    <Table.Td>
                      {neighbor.outgoing_cost ?? "Unavailable"}
                    </Table.Td>
                    <Table.Td>
                      {neighbor.depth ?? "?"} / {neighbor.age_periods ?? "?"}{" "}
                      periods
                    </Table.Td>
                    <Table.Td>
                      {neighbor.rx_on_when_idle == null
                        ? "Unknown"
                        : neighbor.rx_on_when_idle
                          ? "Yes"
                          : "No"}
                    </Table.Td>
                    <Table.Td>
                      {neighbor.device_timeout_seconds == null
                        ? "Unavailable"
                        : `${neighbor.device_timeout_seconds}s`}
                    </Table.Td>
                    <Table.Td>
                      {neighbor.timeout_ms == null
                        ? "Unavailable"
                        : `${neighbor.timeout_ms}ms`}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        ) : (
          <Text c="dimmed">
            No coordinator neighbor entries are currently reported.
          </Text>
        )}
      </Paper>

      <Paper withBorder p="md" mb="xl">
        <Group mb="sm">
          <Route size={18} />
          <Title order={3}>Routing tables</Title>
        </Group>
        {snapshot?.routes?.length ? (
          <Table.ScrollContainer minWidth={520}>
            <Table striped>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Destination</Table.Th>
                  <Table.Th>Next hop</Table.Th>
                  <Table.Th>State</Table.Th>
                  <Table.Th>Route record</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {snapshot.routes.map((route) => (
                  <Table.Tr
                    key={`${route.destination_nwk}-${route.next_hop_nwk}`}
                  >
                    <Table.Td>{shortAddress(route.destination_nwk)}</Table.Td>
                    <Table.Td>{shortAddress(route.next_hop_nwk)}</Table.Td>
                    <Table.Td>
                      {[
                        "Active",
                        "Discovery underway",
                        "Discovery failed",
                        "Inactive",
                      ][route.state] || "Unknown"}
                    </Table.Td>
                    <Table.Td>
                      {route.route_record_required ? "Required" : "No"}
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        ) : (
          <Text c="dimmed">
            No route entries are currently reported by the coordinator.
          </Text>
        )}
        {!!snapshot?.route_records?.length && (
          <Text size="sm" mt="sm">
            Source routes recorded: {snapshot.route_records.length} ·{" "}
            {snapshot.route_records
              .map(
                (r) =>
                  `${shortAddress(r.destination_nwk)} (${(r.path || []).map(shortAddress).join(" → ")})`,
              )
              .join("; ")}
          </Text>
        )}
      </Paper>

      <Paper withBorder p="md" mb="xl">
        <Group justify="space-between" mb="sm">
          <div>
            <Group>
              <Activity size={18} />
              <Title order={3}>Recorded signal performance</Title>
            </Group>
            <Text size="sm" c="dimmed">
              Passive reception samples stored by the Raspberry Pi.
            </Text>
          </div>
          <Select
            aria-label="Sensor for signal history"
            placeholder="Select a device"
            data={devices.map((device) => ({
              value: device.ieee,
              label: device.name,
            }))}
            value={selected}
            onChange={setSelected}
            w={{ base: "100%", sm: 260 }}
          />
        </Group>
        {selectedDevice ? (
          <>
            <Metric
              label={`${selectedDevice.name} · latest coordinator RSSI`}
              value={latestRssi == null ? "No sample" : `${latestRssi} dBm`}
              detail={
                selectedDevice.signal?.received_at
                  ? `Received ${new Date(selectedDevice.signal.received_at * 1000).toLocaleString()} · ${selectedDevice.signal.quality}`
                  : "No signal sample has been recorded"
              }
            />
            {history?.error ? (
              <Alert color="orange" mt="md">
                Signal history unavailable: {history.error}
              </Alert>
            ) : (
              <div className="radio-chart-wrap">
                {history ? (
                  <SignalChart history={history} />
                ) : (
                  <Text c="dimmed" size="sm">
                    Loading signal history…
                  </Text>
                )}
              </div>
            )}
          </>
        ) : (
          <Text c="dimmed">No registered devices are available.</Text>
        )}
      </Paper>

      <Paper withBorder p="md">
        <Group mb="sm">
          <Radio size={18} />
          <Title order={3}>Radio counters and limits</Title>
        </Group>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          <Metric
            label="Retries / delivery failures"
            value="Not exposed"
            detail="Current gateway firmware does not provide Zigbee MAC retry or delivery counters."
          />
          <Metric
            label="Channel utilization / noise"
            value="Not exposed"
            detail="No channel occupancy or noise-floor measurement is available from the current radio API."
          />
        </SimpleGrid>
        <Text size="xs" c="dimmed" mt="md">
          <Radio size={13} /> Local-table snapshot age:{" "}
          {age == null ? "unknown" : `${age} seconds`} ·{" "}
          {snapshot?.neighbor_source || "Source unavailable"}
        </Text>
      </Paper>
    </section>
  );
}
