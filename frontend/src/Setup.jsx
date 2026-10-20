import { useEffect, useState } from "react";
import {
  Accordion,
  Alert,
  Badge,
  Button,
  Group,
  NumberInput,
  Paper,
  Select,
  Stack,
  Tabs,
  Text,
  TextInput,
} from "@mantine/core";
import { useAction, Feedback } from "./actions.jsx";
import ConfigForm from "./ConfigForm.jsx";
import SensorControls from "./SensorControls.jsx";
import PlugControls from "./PlugControls.jsx";
import StarlinkSettings from "./StarlinkSettings.jsx";
import { age, display } from "./layout.js";
function useAdminData(request) {
  const [data, setData] = useState({
    jobs: [],
    displayJobs: [],
    profiles: null,
    error: "",
  });
  useEffect(() => {
    let stopped = false,
      timer;
    const controller = new AbortController();
    let profiles = null;
    const tick = async () => {
      try {
        const [jobs, display, reference] = await Promise.all([
          request("/api/v2/commissioning", { signal: controller.signal }),
          request("/api/v2/display", { signal: controller.signal }),
          profiles
            ? Promise.resolve({ data: profiles })
            : request("/api/v2/sensor-profiles", { signal: controller.signal }),
        ]);
        if (stopped) return;
        profiles = reference.data;
        setData({
          jobs: jobs.data.jobs,
          displayJobs: display.data.jobs,
          profiles,
          error: "",
        });
      } catch (e) {
        if (!stopped && e.name !== "AbortError")
          setData((d) => ({ ...d, error: e.message }));
      } finally {
        if (!stopped) timer = setTimeout(tick, 3000);
      }
    };
    tick();
    return () => {
      stopped = true;
      clearTimeout(timer);
      controller.abort();
    };
  }, [request]);
  return data;
}
function Rename({ name, label, onSave, onDelete, disabled }) {
  const [value, setValue] = useState(name);
  useEffect(() => setValue(name), [name]);
  return (
    <form
      className="settings-row"
      onSubmit={(e) => {
        e.preventDefault();
        onSave(value);
      }}
    >
      <TextInput
        label={label}
        aria-label={label}
        value={value}
        maxLength={80}
        required
        onChange={(e) => setValue(e.currentTarget.value)}
      />
      <Button type="submit" variant="light">
        Save name
      </Button>
      {onDelete && (
        <Button variant="default" disabled={disabled} onClick={onDelete}>
          Delete
        </Button>
      )}
    </form>
  );
}
function Profiles({ api }) {
  const [name, setName] = useState(""),
    action = useAction(api.request);
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Profiles personalise layouts without logins or roles. Devices, locations
        and history are shared. Switching profiles discards unsaved edits.
      </Text>
      <form
        className="settings-row"
        onSubmit={async (e) => {
          e.preventDefault();
          if (await action.run("/api/v2/profiles", { name })) setName("");
        }}
      >
        <TextInput
          label="New profile name"
          aria-label="New profile name"
          maxLength={80}
          required
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
        />
        <Button type="submit" loading={action.busy}>
          Add profile
        </Button>
      </form>
      {api.snapshot.profiles.map((p) =>
        p.default ? (
          <Text key={p.id}>Admin · Permanent default profile</Text>
        ) : (
          <Rename
            key={p.id}
            name={p.name}
            label={"Rename profile " + p.name}
            onSave={(name) =>
              action.run("/api/v2/profiles/" + p.id, { name }, "PUT")
            }
            onDelete={async () => {
              if (await action.run("/api/v2/profiles/" + p.id, null, "DELETE"))
                if (api.profile === p.id) api.chooseProfile("admin");
            }}
          />
        ),
      )}
      <Feedback action={action} />
    </Stack>
  );
}
function Spaces({ api }) {
  const [name, setName] = useState(""),
    action = useAction(api.request);
  const { configuration, devices } = api.snapshot;
  const run = (path, body, method) =>
    action.perform(async () => {
      const result = await api.request("/api/v1/" + path, {
        method,
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      await api.reload();
      setName("");
      return result;
    });

  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Each location gets a tab. Move assigned devices before deleting a
        location.
      </Text>
      <form
        className="settings-row"
        onSubmit={(e) => {
          e.preventDefault();
          run("locations", { name }, "POST");
        }}
      >
        <TextInput
          label="New location"
          aria-label="New location"
          maxLength={80}
          required
          value={name}
          onChange={(e) => setName(e.currentTarget.value)}
        />
        <Button type="submit" loading={action.busy}>
          Add location
        </Button>
      </form>
      {configuration.data.locations.map((l) => (
        <Rename
          key={l.id}
          name={l.name}
          label={"Rename " + l.name}
          disabled={devices.some((d) => d.location_id === l.id)}
          onSave={(name) => run("locations/" + l.id, { name }, "PUT")}
          onDelete={() => run("locations/" + l.id, null, "DELETE")}
        />
      ))}
      <Feedback action={action} />
    </Stack>
  );
}
function Device({ device, view, api, online, admin }) {
  const action = useAction(api.request),
    gateway = api.snapshot.state.gateway,
    configuration = api.snapshot.configuration;
  const command = (body) => action.run("/api/v1/commands", body);
  return (
    <Stack>
      <Text size="xs" c="dimmed">
        {device.ieee} · {device.active ? "Registered" : "Left network"} ·{" "}
        {view?.profile || "Generic / identity not established"}
      </Text>
      <ConfigForm
        api={api}
        configuration={configuration}
        label="Save device settings"
        initial={(c) => ({
          name: c.devices[device.ieee]?.name || "",
          freshness: c.devices[device.ieee]?.freshness_seconds || 3600,
          location: c.devices[device.ieee]?.location_id || "",
        })}
        apply={(c, v) => {
          if (!c.devices[device.ieee])
            throw Error("Device no longer available.");
          const setting = c.devices[device.ieee];
          if (v.name.trim()) setting.name = v.name.trim();
          else delete setting.name;
          setting.freshness_seconds = v.freshness;
          setting.location_id = v.location || null;
        }}
      >
        {(v, set) => (
          <div className="settings-fields">
            <TextInput
              label="Device name"
              aria-label={"Name for " + device.ieee}
              maxLength={80}
              value={v.name}
              onChange={(e) => set("name", e.currentTarget.value)}
            />
            <NumberInput
              label="Reading freshness (seconds)"
              aria-label={"Freshness seconds for " + device.ieee}
              value={v.freshness}
              required
              min={60}
              max={604800}
              onChange={(value) => set("freshness", value)}
            />
            <Select
              label="Location"
              aria-label={"Location for " + device.ieee}
              value={v.location}
              data={[
                { value: "", label: "Unassigned" },
                ...configuration.data.locations.map((l) => ({
                  value: l.id,
                  label: l.name,
                })),
              ]}
              onChange={(value) => set("location", value)}
            />
          </div>
        )}
      </ConfigForm>
      <div className="device-measurement-list">
        {view?.measurements.map((m) => (
          <Text size="sm" key={[m.endpoint, m.cluster, m.attribute].join(":")}>
            {m.label} · EP {m.endpoint}:{" "}
            <strong>
              {display(m, configuration.data.dashboard.temperature_unit).value}{" "}
              {display(m, configuration.data.dashboard.temperature_unit).unit}
            </strong>{" "}
            · {m.quality} · {age(m.received_at)}
            {m.low_battery ? " · Low battery" : ""}
          </Text>
        ))}
      </div>
      <Group>
        <Button
          disabled={!online || !device.active || action.busy}
          onClick={() => command({ op: "discover", ieee: device.ieee })}
        >
          Discover
        </Button>
        {Object.entries(device.endpoints).flatMap(([ep, desc]) => {
          const sensor =
              desc.device_id === 770 ||
              view?.profile?.startsWith("SONOFF SNZB-02"),
            buttons = [];
          if (desc.input_clusters.includes(6) && !sensor && !view?.plug)
            for (const state of [true, false])
              buttons.push(
                <Button
                  key={ep + ":" + state}
                  variant="light"
                  disabled={!online || !device.active || action.busy}
                  onClick={() =>
                    command({
                      op: "on_off",
                      ieee: device.ieee,
                      endpoint: Number(ep),
                      state,
                    })
                  }
                >
                  {state ? "On" : "Off"} · EP {ep}
                </Button>,
              );
          for (const cluster of desc.input_clusters.filter(
            (c) => [6, 1026, 1029].includes(c) && (c !== 6 || !sensor),
          ))
            buttons.push(
              <Button
                key={ep + ":read:" + cluster}
                variant="default"
                disabled={!online || !device.active || action.busy}
                onClick={() =>
                  command({
                    op: "read",
                    ieee: device.ieee,
                    endpoint: Number(ep),
                    cluster,
                    attribute: 0,
                  })
                }
              >
                Read{" "}
                {cluster === 1026
                  ? "temperature"
                  : cluster === 1029
                    ? "humidity"
                    : "state"}{" "}
                · EP {ep}
              </Button>,
            );
          return buttons;
        })}
      </Group>
      <Feedback action={action} />
      {!view?.plug && (
        <SensorControls
          device={device}
          view={view}
          api={api}
          online={online && !admin.error}
          gateway={gateway}
          jobs={admin.jobs}
          displayJobs={admin.displayJobs}
          profiles={admin.profiles}
        />
      )}
      <PlugControls
        device={view || {}}
        request={api.request}
        online={online}
        gateway={gateway}
      />
      <details>
        <summary>Endpoints and raw attributes</summary>
        <pre>
          {JSON.stringify(
            { endpoints: device.endpoints, attributes: device.attributes },
            null,
            2,
          )}
        </pre>
      </details>
    </Stack>
  );
}
function Diagnostics({ api, admin }) {
  const [events, setEvents] = useState(null),
    action = useAction(api.request);
  return (
    <Stack>
      <Text size="sm" c="dimmed">
        Network diagnostics show the latest authenticated response, or cached
        state during an outage.
      </Text>
      <pre>{JSON.stringify(api.snapshot.state.gateway, null, 2)}</pre>
      <details>
        <summary>Sensor capability profiles</summary>
        <Text size="sm" c="dimmed">
          Static capabilities are not per-unit hardware certification.
        </Text>
        <pre>{JSON.stringify(admin.profiles, null, 2)}</pre>
      </details>
      <Button
        variant="default"
        loading={action.busy}
        onClick={async () => {
          const result = await action.run("/api/v1/events");
          if (result) setEvents(result.data.events.slice(0, 20));
        }}
      >
        Load recent events
      </Button>
      {events && (
        <pre>
          {events
            .map(
              (e) =>
                new Date(e.received * 1000).toLocaleString() +
                " · " +
                e.type +
                " · " +
                (e.ieee || ""),
            )
            .join("\n")}
        </pre>
      )}
      <Feedback action={action} />
    </Stack>
  );
}
export default function Setup({ api, online, onLayout }) {
  const admin = useAdminData(api.request),
    [tab, setTab] = useState("gateway"),
    [selected, setSelected] = useState(null),
    action = useAction(api.request);
  const { state, configuration, devices } = api.snapshot,
    gateway = state.gateway;
  return (
    <section id="setup-overview">
      <div className="overview-heading">
        <div>
          <h2>Configuration & Setup</h2>
          <p>
            Manage connected devices and shared spaces. Save edits before
            leaving this page.
          </p>
        </div>
      </div>
      {admin.error && (
        <Alert color="orange" mb="md">
          Job status unavailable: {admin.error}
        </Alert>
      )}
      <Tabs value={tab} onChange={setTab} keepMounted={false}>
        <Tabs.List className="setup-sections">
          {[
            ["gateway", "Gateway"],
            ["starlink", "Starlink"],
            ["devices", "Devices"],
            ["spaces", "Locations"],
            ["profiles", "Profiles"],
            ["preferences", "Preferences"],
            ["diagnostics", "Diagnostics"],
          ].map(([value, label]) => (
            <Tabs.Tab key={value} value={value}>
              {label}
            </Tabs.Tab>
          ))}
        </Tabs.List>
        <Tabs.Panel value="gateway" pt="xl">
          <Paper withBorder p="lg">
            <div className="gateway-counters">
              <div>
                <Text size="xs" c="dimmed">
                  Gateway
                </Text>
                <strong>{online ? "Connected" : "Offline / starting"}</strong>
              </div>
              <div>
                <Text size="xs" c="dimmed">
                  Zigbee channel
                </Text>
                <strong>{gateway.channel || "—"}</strong>
              </div>
              <div>
                <Text size="xs" c="dimmed">
                  Pairing window
                </Text>
                <strong>
                  {gateway.join_seconds
                    ? gateway.join_seconds + "s remaining"
                    : "Closed"}
                </strong>
              </div>
            </div>
            <Group mt="lg">
              <Button
                disabled={!online || action.busy}
                onClick={() =>
                  action.run("/api/v1/commands", {
                    op: "permit_join",
                    seconds: 60,
                  })
                }
              >
                Pair for 60 seconds
              </Button>
              <Button
                variant="default"
                disabled={!online || action.busy}
                onClick={() =>
                  action.run("/api/v1/commands", {
                    op: "permit_join",
                    seconds: 0,
                  })
                }
              >
                Close pairing
              </Button>
            </Group>
            <Text size="sm" mt="md" c="dimmed">
              Pair one device at a time. Pairing alone does not configure
              reporting. Existing network and credentials remain configured
              locally.
            </Text>
            <Feedback action={action} />
          </Paper>
        </Tabs.Panel>
        <Tabs.Panel value="starlink" pt="xl">
          <StarlinkSettings api={api} />
        </Tabs.Panel>
        <Tabs.Panel value="devices" pt="xl">
          <Accordion
            value={selected}
            onChange={setSelected}
            variant="separated"
          >
            {state.devices.map((d) => (
              <Accordion.Item value={d.ieee} key={d.ieee}>
                <Accordion.Control>
                  {devices.find((v) => v.ieee === d.ieee)?.name || d.ieee}
                </Accordion.Control>
                <Accordion.Panel>
                  {selected === d.ieee && (
                    <Device
                      key={d.ieee}
                      device={d}
                      view={devices.find((v) => v.ieee === d.ieee)}
                      api={api}
                      online={online}
                      admin={admin}
                    />
                  )}
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
          {!state.devices.length && <Text>No devices registered yet.</Text>}
        </Tabs.Panel>
        <Tabs.Panel value="spaces" pt="xl">
          <Spaces api={api} />
        </Tabs.Panel>
        <Tabs.Panel value="profiles" pt="xl">
          <Profiles api={api} />
        </Tabs.Panel>
        <Tabs.Panel value="preferences" pt="xl">
          <Paper withBorder p="lg">
            <ConfigForm
              api={api}
              configuration={configuration}
              label="Save preferences"
              initial={(c) => ({
                title: c.dashboard.title,
                unit: c.dashboard.temperature_unit,
              })}
              apply={(c, v) => {
                c.dashboard.title = v.title;
                c.dashboard.temperature_unit = v.unit;
              }}
            >
              {(v, set) => (
                <div className="settings-fields">
                  <TextInput
                    label="Dashboard title"
                    aria-label="Dashboard title"
                    value={v.title}
                    maxLength={80}
                    required
                    onChange={(e) => set("title", e.currentTarget.value)}
                  />
                  <Select
                    label="Temperature display"
                    value={v.unit}
                    data={[
                      { value: "celsius", label: "Celsius · °C" },
                      { value: "fahrenheit", label: "Fahrenheit · °F" },
                    ]}
                    onChange={(value) => set("unit", value)}
                  />
                </div>
              )}
            </ConfigForm>
            <Button mt="xl" variant="light" onClick={onLayout}>
              Edit All dashboard layout
            </Button>
          </Paper>
        </Tabs.Panel>
        <Tabs.Panel value="diagnostics" pt="xl">
          <Diagnostics api={api} admin={admin} />
        </Tabs.Panel>
      </Tabs>
    </section>
  );
}
