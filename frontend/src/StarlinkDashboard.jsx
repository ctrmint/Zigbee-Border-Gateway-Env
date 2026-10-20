import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Paper,
  SimpleGrid,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { Activity, RefreshCw, Router } from "lucide-react";

function age(value) {
  if (!value) return "No successful sample";
  const seconds = Math.max(0, Math.floor(Date.now() / 1000 - value));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function Metric({ label, value, detail }) {
  return (
    <Card withBorder padding="md" className="starlink-metric">
      <Text size="xs" c="dimmed">{label}</Text>
      <Text fw={700} size="lg">{value ?? "Unavailable"}</Text>
      {detail && <Text size="xs" c="dimmed">{detail}</Text>}
    </Card>
  );
}

const SERIES = [
  ["clients_ethernet", "Ethernet", "starlink-line-ethernet"],
  ["clients_2ghz", "2.4 GHz", "starlink-line-2ghz"],
  ["clients_5ghz", "5 GHz", "starlink-line-5ghz"],
];

function ClientChart({ history = [] }) {
  const values = SERIES.flatMap(([key]) =>
    history.filter((sample) => sample.status === "available" && Number.isFinite(sample[key])).map((sample) => sample[key]),
  );
  if (values.length < 2)
    return <Text size="sm" c="dimmed">Not enough successful samples to draw a trend.</Text>;
  const min = Math.min(0, ...values),
    max = Math.max(1, ...values),
    span = max - min || 1;
  const coords = (index, value) => `${(index * 300) / Math.max(1, history.length - 1)},${94 - ((value - min) / span) * 78}`;
  const seriesLines = SERIES.map(([key, label, className]) => {
    const segments = [];
    let segment = [];
    history.forEach((sample, index) => {
      const value = sample.status === "available" ? sample[key] : null;
      if (!Number.isFinite(value)) {
        if (segment.length > 1) segments.push(segment);
        segment = [];
      } else segment.push(coords(index, value));
    });
    if (segment.length > 1) segments.push(segment);
    return { label, className, segments };
  });
  const valid = history.filter((sample) => sample.status === "available");
  return (
    <>
      <svg className="starlink-chart" viewBox="0 0 300 110" role="img" aria-label="Connected Starlink router client counts by band over the last seven days">
        <line x1="0" y1="94" x2="300" y2="94" className="starlink-chart-axis" />
        {seriesLines.flatMap((line) => line.segments.map((segment, index) => (
          <polyline key={`${line.label}-${index}`} points={segment.join(" ")} fill="none" className={line.className} />
        )))}
      </svg>
      <Group gap="md" wrap="wrap" className="starlink-chart-legend">
        {seriesLines.map((line) => <Text key={line.label} size="xs" className={line.className}>{line.label}</Text>)}
      </Group>
      <Group justify="space-between" mt="xs">
        <Text size="xs" c="dimmed">{new Date(valid[0].received_at * 1000).toLocaleString()}</Text>
        <Text size="xs" c="dimmed">{new Date(valid.at(-1).received_at * 1000).toLocaleString()}</Text>
      </Group>
      <Text size="xs" c="dimmed" mt={4}>
        Samples are collected once per minute. Lines break across failed or unsupported polls.
      </Text>
    </>
  );
}

function PerformanceChart({ history = [], fields, label, format = (value) => value.toFixed(1) }) {
  const valid = history.filter((point) => point.status === "available" && fields.some(([key]) => Number.isFinite(point[key])));
  if (valid.length < 2)
    return <Text size="sm" c="dimmed">Collecting dish samples; a trend will appear after two successful polls.</Text>;
  const values = fields.flatMap(([key]) => valid.map((point) => point[key]).filter(Number.isFinite));
  const min = Math.min(0, ...values), max = Math.max(1, ...values), span = max-min || 1;
  const coords = (index, value) => `${(index * 300) / Math.max(1, history.length - 1)},${94 - ((value-min)/span)*78}`;
  return (
    <>
      <svg className="starlink-chart" viewBox="0 0 300 110" role="img" aria-label={label}>
        <line x1="0" y1="94" x2="300" y2="94" className="starlink-chart-axis" />
        {fields.map(([key, name, color]) => {
          const segments=[]; let segment=[];
          history.forEach((point,index) => {
            const value=point.status === "available" ? point[key] : null;
            if (!Number.isFinite(value)) { if(segment.length>1)segments.push(segment); segment=[]; }
            else segment.push(coords(index,value));
          });
          if(segment.length>1)segments.push(segment);
          return segments.map((points,index)=><polyline key={`${key}-${index}`} points={points.join(" ")} fill="none" className={color}/>);
        })}
      </svg>
      <Group gap="md" wrap="wrap" className="starlink-chart-legend">
        {fields.map(([key,name,color])=><Text key={key} size="xs" className={color}>{name}</Text>)}
      </Group>
      <Group justify="space-between" mt="xs">
        <Text size="xs" c="dimmed">{new Date(valid[0].received_at*1000).toLocaleString()}</Text>
        <Text size="xs" c="dimmed">{new Date(valid.at(-1).received_at*1000).toLocaleString()}</Text>
      </Group>
      <Text size="xs" c="dimmed" mt={4}>{valid.length} retained samples shown · current value {format(valid.slice().reverse().find((point)=>Number.isFinite(point[fields[0][0]]))?.[fields[0][0]])}</Text>
    </>
  );
}

function statusMessage(snapshot) {
  if (snapshot.status === "disabled") return "Starlink monitoring is disabled. Enable it in Configuration & Setup → Starlink.";
  if (snapshot.status === "unsupported") return "This router or firmware does not implement the documented diagnostics response.";
  if (snapshot.status === "stale") return `The latest router poll failed (${snapshot.error || "unavailable"}). Showing the last successful sample from ${age(snapshot.observed_at)}.`;
  if (snapshot.error === "dependency_missing") return "The optional gRPC runtime is missing on the dashboard host. Install the Starlink requirements and restart the dashboard service.";
  if (snapshot.status === "unavailable") return `The router has not returned diagnostics yet (${snapshot.error || "unavailable"}). Check the configured private address, port, and local network connection.`;
  return "";
}

function dishStatusMessage(dish) {
  if (dish.status === "disabled") return "Dish telemetry is disabled. Enable it in Configuration & Setup → Starlink.";
  if (dish.status === "unsupported") return "The terminal did not return the expected read-only status response.";
  if (dish.status === "stale") return `The latest dish poll failed (${dish.error || "unavailable"}). Showing its last successful sample from ${age(dish.observed_at)}.`;
  if (dish.error === "dependency_missing") return "The optional gRPC runtime is missing on the dashboard host.";
  if (dish.status === "unavailable") return `Dish telemetry is unavailable (${dish.error || "unavailable"}). Check the dish address and local route.`;
  return "";
}

function rateMbps(value) {
  return Number.isFinite(value) ? `${(value / 1_000_000).toFixed(2)} Mbps` : "Unavailable";
}

export default function StarlinkDashboard({ api }) {
  const [snapshot, setSnapshot] = useState(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const refresh = useCallback(async (signal) => {
    setBusy(true);
    try {
      const result = await api.request("/api/v2/starlink", { signal });
      setSnapshot(result.data);
      setError("");
    } catch (e) {
      if (e.name !== "AbortError") setError(e.message);
    } finally {
      setBusy(false);
    }
  }, [api.request]);
  useEffect(() => {
    const controller = new AbortController();
    refresh(controller.signal);
    const timer = setInterval(() => refresh(), 30000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [refresh]);
  const networks = snapshot?.networks || [];
  const totals = useMemo(() => {
    const sum = (key) => {
      const values = networks.map((network) => network[key]).filter(Number.isFinite);
      return values.length ? values.reduce((total, value) => total + value, 0) : null;
    };
    return { ethernet: sum("clients_ethernet"), wifi24: sum("clients_2ghz"), wifi5: sum("clients_5ghz") };
  }, [networks]);
  const alert = snapshot && statusMessage(snapshot);
  const dish = snapshot?.dish;
  const dishAlert = dish && dishStatusMessage(dish);
  const metrics = dish?.metrics || {};
  const totalClients = Object.values(totals).some(Number.isFinite)
    ? Object.values(totals).reduce((total, count) => total + (count || 0), 0)
    : null;
  return (
    <section className="starlink-dashboard" aria-label="Starlink router monitoring">
      <Group justify="space-between" align="flex-end" mb="lg">
        <div>
          <Text className="eyebrow">LOCAL ROUTER DIAGNOSTICS</Text>
          <Title order={2}>Starlink</Title>
          <Text c="dimmed" size="sm">Read-only status from the Starlink router’s local gRPC API.</Text>
        </div>
        <Button variant="light" leftSection={<RefreshCw size={16} />} onClick={() => refresh()} loading={busy}>
          Refresh view
        </Button>
      </Group>
      {error && <Alert color="red" mb="md" title="Starlink information refresh failed">{error}</Alert>}
      {alert && <Alert color={snapshot.status === "disabled" ? "blue" : "orange"} mb="md" title={snapshot.status === "disabled" ? "Monitoring disabled" : snapshot.status === "stale" ? "Showing last successful sample" : snapshot.status === "unsupported" ? "Diagnostics unsupported" : "Router unavailable"}>{alert}</Alert>}
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} mb="xl">
        <Metric label="Router connection" value={snapshot?.status === "available" ? "Online" : snapshot?.status === "stale" ? "Stale" : snapshot?.status === "disabled" ? "Disabled" : snapshot?.status === "unsupported" ? "Unsupported" : "Unavailable"} detail={snapshot?.observed_at ? `Last success ${age(snapshot.observed_at)}` : "No successful sample"} />
        <Metric label="Hardware" value={snapshot?.router?.hardware_version} />
        <Metric label="Software" value={snapshot?.router?.software_version} />
        <Metric label="Connected clients" value={totalClients} detail={`${totals.ethernet ?? "—"} wired · ${(totals.wifi24 ?? 0) + (totals.wifi5 ?? 0)} Wi-Fi`} />
      </SimpleGrid>
      <div className="starlink-panels">
        <Paper withBorder p="lg">
          <Group justify="space-between" mb="md">
            <div><Title order={3}>Network links</Title><Text size="sm" c="dimmed">Router diagnostic network records</Text></div>
            <Badge variant="light">{networks.length} networks</Badge>
          </Group>
          {networks.length ? (
            <div className="starlink-table-wrap"><Table.ScrollContainer minWidth={600}><Table striped highlightOnHover>
              <Table.Thead><Table.Tr><Table.Th>Domain</Table.Th><Table.Th>IPv4</Table.Th><Table.Th>IPv6 prefixes</Table.Th><Table.Th>Ethernet</Table.Th><Table.Th>2.4 GHz</Table.Th><Table.Th>5 GHz</Table.Th></Table.Tr></Table.Thead>
              <Table.Tbody>{networks.map((network, index) => <Table.Tr key={`${network.domain}-${index}`}>
                <Table.Td>{network.domain || "—"}</Table.Td><Table.Td>{network.ipv4 || "—"}</Table.Td>
                <Table.Td>{network.ipv6?.length ? network.ipv6.join(", ") : "—"}</Table.Td>
                <Table.Td>{network.clients_ethernet ?? "—"}</Table.Td><Table.Td>{network.clients_2ghz ?? "—"}</Table.Td><Table.Td>{network.clients_5ghz ?? "—"}</Table.Td>
              </Table.Tr>)}</Table.Tbody>
            </Table></Table.ScrollContainer></div>
          ) : <Text size="sm" c="dimmed">Network diagnostics will appear when the router returns a supported sample.</Text>}
        </Paper>
        <Paper withBorder p="lg">
          <Group mb="md"><Activity size={18} /><div><Title order={3}>Client-count history</Title><Text size="sm" c="dimmed">Up to seven days of once-per-minute samples</Text></div></Group>
          <ClientChart history={snapshot?.history} />
        </Paper>
      </div>
      <Paper withBorder p="lg" mt="lg" className="starlink-dish-panel">
        <Group justify="space-between" mb="md">
          <div><Text className="eyebrow">DISH TERMINAL · READ ONLY</Text><Title order={3}>Satellite link performance</Title></div>
          <Badge color={dish?.status === "available" ? "teal" : "gray"} variant="light">{dish?.status || "unavailable"}</Badge>
        </Group>
        {dishAlert && <Alert color={dish.status === "disabled" ? "blue" : "orange"} mb="md" title={dish.status === "disabled" ? "Dish telemetry disabled" : dish.status === "stale" ? "Showing last successful dish sample" : "Dish telemetry unavailable"}>{dishAlert}</Alert>}
        <SimpleGrid cols={{ base: 2, xs: 3, lg: 6 }} mb="lg">
          <Metric label="Dish link state" value={metrics.state || "Unavailable"} detail={dish?.observed_at ? `Updated ${age(dish.observed_at)}` : "No successful sample"} />
          <Metric label="Download" value={rateMbps(metrics.downlink_throughput_bps)} />
          <Metric label="Upload" value={rateMbps(metrics.uplink_throughput_bps)} />
          <Metric label="PoP latency" value={Number.isFinite(metrics.pop_ping_latency_ms) ? `${metrics.pop_ping_latency_ms.toFixed(1)} ms` : "Unavailable"} />
          <Metric label="Packet loss" value={Number.isFinite(metrics.pop_ping_drop_rate) ? `${(metrics.pop_ping_drop_rate*100).toFixed(2)}%` : "Unavailable"} />
          <Metric label="Obstruction" value={Number.isFinite(metrics.fraction_obstructed) ? `${(metrics.fraction_obstructed*100).toFixed(2)}%` : "Unavailable"} detail={metrics.currently_obstructed === null || metrics.currently_obstructed === undefined ? "Current status unavailable" : metrics.currently_obstructed ? "Currently obstructed" : "Currently clear"} />
        </SimpleGrid>
        <div className="starlink-panels">
          <Paper withBorder p="md"><Title order={4} mb="sm">Dish throughput</Title><Text size="xs" c="dimmed" mb="sm">Actual instantaneous traffic, not a speed test.</Text><PerformanceChart history={dish?.history} fields={[["downlink_throughput_bps","Download","starlink-line-5ghz"],["uplink_throughput_bps","Upload","starlink-line-2ghz"]]} label="Dish downlink and uplink throughput history" format={rateMbps} /></Paper>
          <Paper withBorder p="md"><Title order={4} mb="sm">Latency and packet loss</Title><div className="starlink-dish-series"><PerformanceChart history={dish?.history} fields={[["pop_ping_latency_ms","PoP latency (ms)","starlink-line-ethernet"]]} label="Dish point-of-presence latency history" format={(value)=>`${value.toFixed(1)} ms`} /><PerformanceChart history={dish?.history} fields={[["pop_ping_drop_rate","Packet loss (%)","starlink-line-2ghz"]]} label="Dish packet loss history" format={(value)=>`${(value*100).toFixed(2)}%`} /></div></Paper>
        </div>
        <Text size="xs" c="dimmed" mt="md">Dish status is sampled once per minute. Latency, packet loss, throughput and obstruction are terminal-reported values; throughput is not available capacity.</Text>
      </Paper>
      <Text size="xs" c="dimmed" mt="md">Last poll attempt: {snapshot?.last_attempt_at ? new Date(snapshot.last_attempt_at * 1000).toLocaleString() : "not yet attempted"}. No router settings or connected-client identifiers are collected.</Text>
    </section>
  );
}
