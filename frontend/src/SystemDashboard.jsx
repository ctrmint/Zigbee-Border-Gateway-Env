import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Paper,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import {
  Activity,
  Database,
  HardDrive,
  Network,
  RefreshCw,
  Trash2,
} from "lucide-react";

function prettyBytes(value) {
  if (value == null) return "Unavailable";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let n = value,
    i = 0;
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024;
    i++;
  }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}
function date(value) {
  return value == null ? "No data" : new Date(value * 1000).toLocaleString();
}
function Metric({ label, value, detail }) {
  return (
    <Card withBorder padding="md" className="system-metric">
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

export default function SystemDashboard({ api }) {
  const [host, setHost] = useState(null),
    [database, setDatabase] = useState(null);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [preview, setPreview] = useState(null),
    [purged, setPurged] = useState(null);
  const [check, setCheck] = useState(false);
  const refresh = useCallback(
    async (signal) => {
      try {
        const [h, d] = await Promise.all([
          api.request("/api/v2/system", { signal }),
          api.request("/api/v2/system/database", { signal }),
        ]);
        setHost(h.data);
        setDatabase(d.data);
        setError("");
      } catch (e) {
        if (e.name !== "AbortError") setError(e.message);
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
  async function run(action) {
    setBusy(true);
    setError("");
    try {
      await action();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const names = {
    devices: "Registered devices",
    locations: "Locations",
    profiles: "Profiles",
    events: "Raw events",
    measurements: "Measurements",
    signal_samples: "Signal samples",
    ingestion_gaps: "Ingestion gaps",
    plug_discontinuities: "Plug energy discontinuities",
    commissioning_jobs: "Commissioning jobs",
    display_jobs: "Display jobs",
    plug_jobs: "Plug jobs",
  };
  return (
    <section className="system-dashboard" aria-label="System dashboard">
      <Group justify="space-between" align="flex-end" mb="lg">
        <div>
          <Text className="eyebrow">SYSTEM HEALTH</Text>
          <Title order={2}>Raspberry Pi & database</Title>
          <Text c="dimmed" size="sm">
            Read-only health summary. Host metrics refresh every 30 seconds.
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
        <Alert color="red" mb="md" title="System information unavailable">
          {error}
        </Alert>
      )}
      {host?.warnings?.map((warning) => (
        <Alert key={warning} color="orange" mb="sm">
          {warning}
        </Alert>
      ))}
      <Title order={3} mb="sm">
        <Activity size={18} /> Host health
      </Title>
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} mb="xl">
        <Metric
          label="Platform"
          value={host?.host?.model || "Raspberry Pi model unavailable"}
          detail={`${host?.host?.os || "OS unavailable"} · ${host?.host?.architecture || "architecture unavailable"}`}
        />
        <Metric
          label="Kernel / uptime"
          value={host?.host?.kernel}
          detail={
            host?.host?.uptime_seconds == null
              ? "Host uptime unavailable"
              : `${Math.floor(host.host.uptime_seconds / 86400)} days · time sync ${host.host.time_synchronized == null ? "unknown" : host.host.time_synchronized ? "yes" : "no"}`
          }
        />
        <Metric
          label="CPU"
          value={
            host?.cpu?.utilization_percent == null
              ? "Sampling…"
              : `${host.cpu.utilization_percent}%`
          }
          detail={`Load ${host?.cpu?.load_1_5_15?.map((v) => v.toFixed(2)).join(" / ") || "unavailable"} · ${host?.cpu?.temperature_celsius == null ? "temperature unavailable" : `${host.cpu.temperature_celsius.toFixed(1)} °C`}`}
        />
        <Metric
          label="Memory"
          value={
            host?.memory?.used_percent == null
              ? "Unavailable"
              : `${host.memory.used_percent}% used`
          }
          detail={`${prettyBytes(host?.memory?.total_bytes)} total · swap ${prettyBytes(host?.memory?.swap_free_bytes)} free / ${prettyBytes(host?.memory?.swap_total_bytes)} total`}
        />
        <Metric
          label="Root filesystem"
          value={
            host?.disk?.used_percent == null
              ? "Unavailable"
              : `${host.disk.used_percent}% used`
          }
          detail={`${prettyBytes(host?.disk?.free_bytes)} free of ${prettyBytes(host?.disk?.total_bytes)}`}
        />
        <Metric
          label="Dashboard process"
          value={host?.host?.process?.state || "Unavailable"}
          detail={`PID ${host?.host?.process?.pid ?? "unknown"} · running ${host?.host?.process?.uptime_seconds ?? "unknown"}s · restart count unavailable`}
        />
        <Metric
          label="Service manager"
          value="Unavailable"
          detail="No systemd privilege or restart-history integration"
        />
        <Metric
          label="Network time"
          value={
            host?.host?.time_synchronized == null
              ? "Unknown"
              : host.host.time_synchronized
                ? "Synchronized"
                : "Not synchronized"
          }
          detail="System service manager status is not exposed to the dashboard"
        />
      </SimpleGrid>
      <Paper withBorder p="md" mb="xl">
        <Group mb="sm">
          <Network size={18} />
          <Title order={3}>Network interfaces</Title>
        </Group>
        {host?.interfaces?.length ? (
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Interface</Table.Th>
                <Table.Th>Link</Table.Th>
                <Table.Th>IPv4</Table.Th>
                <Table.Th>IPv6</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {host.interfaces.map((iface) => (
                <Table.Tr key={iface.name}>
                  <Table.Td>{iface.name}</Table.Td>
                  <Table.Td>{iface.state || "Unavailable"}</Table.Td>
                  <Table.Td>{iface.ipv4?.join(", ") || "Unavailable"}</Table.Td>
                  <Table.Td>{iface.ipv6?.join(", ") || "Unavailable"}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Text c="dimmed">Interface data unavailable.</Text>
        )}
      </Paper>
      <Group justify="space-between" mb="sm">
        <Group>
          <Database size={18} />
          <Title order={3}>SQLite database</Title>
        </Group>
        <Badge color={database?.integrity?.status === "ok" ? "teal" : "gray"}>
          Integrity: {database?.integrity?.status || "unavailable"}
        </Badge>
      </Group>
      <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }} mb="md">
        <Metric
          label="Database file"
          value={prettyBytes(database?.file_size_bytes)}
          detail={`WAL ${prettyBytes(database?.wal_size_bytes)} · journal ${prettyBytes(database?.journal_size_bytes)}`}
        />
        <Metric
          label="Pages"
          value={
            database ? database.page_count.toLocaleString() : "Unavailable"
          }
          detail={`${prettyBytes((database?.page_size || 0) * (database?.free_pages || 0))} free pages · ${database?.journal_mode || "mode unavailable"}`}
        />
        <Metric
          label="Latest ingestion"
          value={date(database?.latest_ingestion_at)}
          detail="Most recent gateway event persisted"
        />
        <Metric
          label="Integrity check"
          value={date(database?.integrity?.checked_at)}
          detail={database?.integrity?.summary || "Run an explicit quick check"}
        />
      </SimpleGrid>
      <Paper withBorder p="md" mb="xl">
        <Title order={4} mb="sm">
          Stored records
        </Title>
        <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
          {Object.entries(database?.counts || {}).map(([key, value]) => (
            <Metric
              key={key}
              label={names[key] || key}
              value={value.toLocaleString()}
            />
          ))}
        </SimpleGrid>
        <Group mt="md">
          <Button
            variant="light"
            leftSection={<Activity size={16} />}
            loading={check}
            onClick={() =>
              run(async () => {
                setCheck(true);
                try {
                  await api.request("/api/v2/system/database/check", {
                    method: "POST",
                    body: "{}",
                  });
                  await refresh();
                } finally {
                  setCheck(false);
                }
              })
            }
          >
            Run database quick check
          </Button>
          <Text size="xs" c="dimmed">
            SQLite quick_check runs only when requested.
          </Text>
        </Group>
      </Paper>
      <Paper withBorder p="md" mb="xl">
        <Title order={4} mb="sm">
          Retained telemetry range
        </Title>
        {Object.keys(database?.retained_range || {}).length ? (
          <Table striped>
            <Table.Thead>
              <Table.Tr>
                <Table.Th>Table</Table.Th>
                <Table.Th>Oldest</Table.Th>
                <Table.Th>Newest</Table.Th>
              </Table.Tr>
            </Table.Thead>
            <Table.Tbody>
              {Object.entries(database.retained_range).map(([table, range]) => (
                <Table.Tr key={table}>
                  <Table.Td>{names[table] || table}</Table.Td>
                  <Table.Td>{date(range.oldest)}</Table.Td>
                  <Table.Td>{date(range.newest)}</Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        ) : (
          <Text c="dimmed">No retained history is available.</Text>
        )}
      </Paper>
      <Paper withBorder p="md">
        <Group mb="xs">
          <HardDrive size={18} />
          <Title order={3}>Historical data retention</Title>
        </Group>
        <Text size="sm" c="dimmed" mb="md">
          History is retained for 60 days. Purging removes only timestamped
          history rows; current device readings and all configuration are
          preserved.
        </Text>
        {purged && (
          <Alert color="teal" mb="md">
            Purged {purged.total_rows} historical rows before{" "}
            {date(purged.cutoff)}.
          </Alert>
        )}
        <Button
          color="red"
          variant="light"
          leftSection={<Trash2 size={16} />}
          loading={busy}
          onClick={() =>
            run(async () => {
              const result = await api.request("/api/v2/system/purge-preview");
              setPreview(result.data);
            })
          }
        >
          Preview purge older than 60 days
        </Button>
        <Text size="xs" c="dimmed" mt="sm">
          Preview is required before deletion. No device commands or Zigbee
          reads are sent.
        </Text>
      </Paper>
      <Modal
        opened={!!preview}
        onClose={() => setPreview(null)}
        title="Confirm historical data purge"
        centered
      >
        {preview && (
          <Stack>
            <Text size="sm">
              Delete recorded history older than {date(preview.cutoff)}? This
              preview expires in five minutes. The operation uses one database
              transaction.
            </Text>
            <Table>
              <Table.Tbody>
                {Object.entries(preview.counts).map(([table, count]) => (
                  <Table.Tr key={table}>
                    <Table.Td>{names[table] || table}</Table.Td>
                    <Table.Td>{count.toLocaleString()}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
            <Alert color="blue">
              Device registry, latest device readings, locations, profiles,
              dashboard settings, and operational job records are preserved.
            </Alert>
            <Group justify="flex-end">
              <Button variant="default" onClick={() => setPreview(null)}>
                Cancel
              </Button>
              <Button
                color="red"
                loading={busy}
                onClick={() =>
                  run(async () => {
                    const result = await api.request("/api/v2/system/purge", {
                      method: "POST",
                      body: JSON.stringify({ preview_id: preview.preview_id }),
                    });
                    setPurged(result.data);
                    setPreview(null);
                    await refresh();
                  })
                }
              >
                Delete listed history
              </Button>
            </Group>
          </Stack>
        )}
      </Modal>
    </section>
  );
}
