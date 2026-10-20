import AppearanceEditor from "./AppearanceEditor.jsx";
import { presentationCSS, seriesColor, metricStyle } from "./presentation.js";
import React, { useState, useEffect, useMemo } from "react";
import { createRoot } from "react-dom/client";
import {
  MantineProvider,
  createTheme,
  Button,
  PasswordInput,
  Select,
  Badge,
  Paper,
  Group,
  Text,
  Title,
  Stack,
  Alert,
  NumberInput,
  SegmentedControl,
  Divider,
  Modal,
} from "@mantine/core";
import {
  House,
  Radio,
  Thermometer,
  PlugZap,
  Droplets,
  ArrowUpRight,
  SlidersHorizontal,
  Sun,
  Moon,
  Signal,
  Grip,
  ArrowLeft,
  LogOut,
  WifiOff,
  BatteryLow,
  LayoutGrid,
  Check,
  RotateCcw,
  Database,
} from "lucide-react";
import "@mantine/core/styles.css";
import "./style.css";
import Grid from "./Grid.jsx";
import Location, { useHistories } from "./Location.jsx";
import { geometry, historyKey } from "./history.js";
const Setup = React.lazy(() => import("./Setup.jsx"));
const SystemDashboard = React.lazy(() => import("./SystemDashboard.jsx"));
import useDashboard from "./useDashboard.js";
import {
  age,
  quality,
  display,
  eligible,
  effectiveLayout,
  emptyLayout,
  breakpoints,
  breakpointFor,
  editItem,
  mergePresent,
} from "./layout.js";

const theme = createTheme({
  primaryColor: "teal",
  defaultRadius: "md",
  fontFamily:
    'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
  headings: { fontFamily: "inherit" },
  components: {
    Button: { defaultProps: { fw: 600 } },
    Select: { defaultProps: { allowDeselect: false } },
  },
});
function Tile({ device, locations, units, layout, history, editing = false }) {
  if (!device) return null; // A departed tile can be removed during the next grid layout effect.
  const location =
    locations.find((l) => l.id === device.location_id)?.name || "Unassigned";
  const measurements = device.measurements.filter(
    (m) => m.cluster !== 6 || device.plug,
  );
  const main = measurements.filter((m) => m.cluster !== 1),
    battery = measurements.filter((m) => m.cluster === 1);
  const stale = main.some((m) => quality(m) !== "valid"),
    multiple = new Set(main.map((m) => m.endpoint)).size > 1;
  const Icon = device.plug ? PlugZap : Thermometer;
  return (
    <article
      className={`reading-card ${device.plug ? "plug-card" : ""}`}
      data-sensor-id={device.ieee}
      aria-label={device.name}
      style={presentationCSS(layout, "all", device.ieee)}
    >
      <header className="reading-header">
        <div className="device-icon">
          <Icon size={20} />
        </div>
        <div className="device-heading">
          <p className="location-label">{location}</p>
          <h3>{device.name}</h3>
        </div>
        {editing ? (
          <span className="tile-handle" aria-hidden="true">
            <Grip size={21} />
          </span>
        ) : (
          <span
            className={`status-dot ${stale ? "needs-attention" : ""}`}
            title={
              stale
                ? "Some readings need attention"
                : "Readings within freshness window"
            }
          />
        )}
      </header>
      <dl className="measurements">
        {main.map((m) => {
          const q = quality(m),
            value = display(m, units);
          return (
            <div
              key={`${m.endpoint}:${m.cluster}:${m.attribute}`}
              className={`measurement ${device.plug && !["W", "on/off"].includes(m.unit) ? "measurement-secondary" : ""} ${value.value.length > 9 ? "measurement-wide" : ""} ${q !== "valid" ? "measurement-warning" : ""}`}
              data-quality={q}
              style={{ "--series-color": seriesColor(m.cluster, m.attribute) }}
            >
              <dt>
                {m.label}
                {multiple ? ` · EP ${m.endpoint}` : ""}
              </dt>
              <dd>
                <span className="measurement-value">{value.value}</span>
                <span className="measurement-unit">{value.unit}</span>
              </dd>
              <p className="measurement-age">
                {q !== "valid"
                  ? `${q === "missing" ? "No reading" : q === "invalid" ? "Invalid reading" : "Stale"} · `
                  : ""}
                {age(m.received_at)}
              </p>
            </div>
          );
        })}
      </dl>
      {history && <MiniTrend history={history} units={units} />}
      {!main.length && (
        <p className="no-reading">Waiting for supported readings.</p>
      )}
      {battery.length > 0 && (
        <div className="battery-strip">
          {battery.map((m) => (
            <span
              key={m.attribute}
              className={m.low_battery ? "warning-text" : ""}
            >
              {m.low_battery && <BatteryLow size={14} />} {m.label}{" "}
              {display(m, units).value}
              {display(m, units).unit} ·{" "}
              {quality(m) !== "valid" ? quality(m) + " · " : ""}
              {age(m.received_at)}
              {m.low_battery ? " · Low battery" : ""}
            </span>
          ))}
        </div>
      )}
      <footer className="reading-footer">
        <Signal size={14} />
        <span>
          {device.signal?.value == null
            ? "Signal not received"
            : `${device.signal.value} dBm · ${quality(device.signal) === "stale" ? "Stale · " : ""}${age(device.signal.received_at)}`}
        </span>
      </footer>
    </article>
  );
}
function MiniTrend({ history, units }) {
  const plot = !history.error && geometry(history, units === "fahrenheit");
  if (!plot) return null;
  return (
    <div
      className="mini-trend"
      style={{ "--series-color": seriesColor(history.cluster) }}
    >
      <svg
        viewBox="48 20 496 164"
        preserveAspectRatio="none"
        role="img"
        aria-label="Recent recorded trend"
      >
        <path d={plot.path} className="history-line" />
      </svg>
      <p>
        {history.metricLabel} · recent hour
        {history.truncated ? " · sample limit reached" : ""}
        {history.gaps.length ? " · recording gaps" : ""}
      </p>
    </div>
  );
}
function App() {
  const api = useDashboard(),
    { snapshot, profile } = api;
  const [locationEditing, setLocationEditing] = useState(false),
    [password, setPassword] = useState(""),
    [page, setPage] = useState("all"),
    [draft, setDraft] = useState(null),
    [base, setBase] = useState(null),
    [saveError, setSaveError] = useState(""),
    [saving, setSaving] = useState(false),
    [confirm, setConfirm] = useState(null),
    [selected, setSelected] = useState(""),
    [screen, setScreen] = useState(() => breakpointFor(window.innerWidth)),
    [editScreen, setEditScreen] = useState("desktop");
  const hasEdits = !!draft || locationEditing;
  useEffect(() => {
    const warn = (e) => {
      if (hasEdits) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasEdits]);
  const configuration = snapshot?.configuration?.data,
    preferences = configuration?.dashboard;
  const settings = preferences?.grid_layout || emptyLayout(),
    scheme = (draft || settings).theme;
  const devices = useMemo(
    () => eligible(snapshot?.devices || [], snapshot?.state.devices || []),
    [snapshot?.devices, snapshot?.state.devices],
  );
  const trendWidgets = useMemo(
    () =>
      page === "all" || page === "editor"
        ? devices
            .slice(0, 50)
            .filter((d) => metricStyle(draft || settings, "all", d.ieee).trend)
            .flatMap((d) => {
              const m =
                d.measurements.find((m) => m.cluster === 1026) ||
                d.measurements.find(
                  (m) => m.cluster !== 1 && typeof m.value === "number",
                );
              return m
                ? [
                    {
                      id: d.ieee,
                      type: "chart",
                      sparkline: true,
                      title: m.label,
                      source: {
                        ieee: d.ieee,
                        endpoint: m.endpoint,
                        cluster: m.cluster,
                        attribute: m.attribute,
                      },
                      time_range: 3600,
                    },
                  ]
                : [];
            })
        : [],
    [devices, page, draft, settings],
  );
  const trends = useHistories(
    trendWidgets,
    snapshot?.devices || [],
    api.request,
    snapshot?.fetched,
  );
  const trendFor = (id) => {
    const w = trendWidgets.find((w) => w.id === id);
    return w && trends[historyKey(w)]
      ? {
          ...trends[historyKey(w)],
          metricLabel: w.title,
          cluster: w.source.cluster,
        }
      : null;
  };
  const legacy = preferences?.all_layout || {
    columns: 0,
    min_tile_width: 240,
    order: [],
  };
  const mode = page === "editor" ? editScreen : screen;
  const items = useMemo(
    () => effectiveLayout(devices, draft || settings, legacy, mode),
    [devices, draft, settings, legacy, mode],
  );
  useEffect(() => {
    const resize = () => setScreen(breakpointFor(window.innerWidth));
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);
  useEffect(() => {
    setDraft(null);
    setBase(null);
    setPage("all");
    setSaveError("");
  }, [profile, api.connected]);
  useEffect(() => {
    document.title = (preferences?.title || "Home") + " · Zigbee dashboard";
  }, [preferences?.title]);
  const online =
    !!snapshot?.state.gateway.connected &&
    !!snapshot?.state.gateway.ready &&
    !api.error;
  function begin() {
    setDraft(structuredClone(settings));
    setBase(snapshot.configuration);
    api.hold.current = true;
    setPage("editor");
    setEditScreen(screen);
    setSelected(devices[0]?.ieee || "");
    setSaveError("");
  }
  function updateItems(current) {
    setDraft((d) =>
      d
        ? {
            ...d,
            all: { ...d.all, [mode]: mergePresent(d.all[mode], current) },
          }
        : d,
    );
  }
  function discard() {
    setDraft(null);
    setBase(null);
    api.hold.current = false;
    setPage("all");
    setSaveError("");
  }
  async function save(reapply = false) {
    setSaving(true);
    setSaveError("");
    try {
      const latest = reapply ? await api.reload() : base;
      await api.saveGrid(draft, latest, base);
      discard();
    } catch (e) {
      if (e.name !== "AbortError")
        setSaveError(
          e.status === 412
            ? "Configuration changed in another session. Reload to discard this edit, or explicitly reapply it to the latest configuration."
            : e.message,
        );
    } finally {
      setSaving(false);
    }
  }
  const currentLocation = configuration?.locations.find(
    (l) => "location:" + l.id === page,
  );
  useEffect(() => {
    if (configuration && page.startsWith("location:") && !currentLocation)
      setPage("all");
  }, [page, configuration, currentLocation]);
  const chosen = items.find((n) => n.id === selected) || items[0];
  function change(patch) {
    if (chosen)
      updateItems(editItem(items, chosen.id, patch, breakpoints[mode]));
  }
  const profileName =
    snapshot?.profiles.find((p) => p.id === profile)?.name || "Admin";
  const staleCount = devices.filter((d) =>
    d.measurements.some((m) => m.cluster !== 1 && quality(m) !== "valid"),
  ).length;
  return (
    <MantineProvider theme={theme} forceColorScheme={scheme}>
      <div className="app-shell">
        <header className="topbar">
          <a
            href="/"
            className="brand"
            onClick={(e) => {
              e.preventDefault();
              if (hasEdits) setConfirm(() => discard);
              else setPage("all");
            }}
          >
            <span className="brand-mark">
              <House size={20} />
            </span>
            <span>
              observatory<span className="brand-subtitle">ZIGBEE HOME</span>
            </span>
          </a>
          {api.connected && snapshot && (
            <Group gap="sm" className="topbar-status">
              <Badge
                color={online ? "teal" : "orange"}
                variant="light"
                leftSection={
                  online ? <span className="live-dot" /> : <WifiOff size={13} />
                }
              >
                {snapshot.state.gateway.mode === "simulator"
                  ? "Simulator · "
                  : ""}
                {online ? "Gateway connected" : "Gateway unavailable"}
              </Badge>
              <Text size="xs" c="dimmed" className="topbar-status-summary">
                {snapshot.state.devices.length} devices registered ·{" "}
                {profileName}
                ’s view
              </Text>
            </Group>
          )}
          <Group gap="md" className="topbar-right">
            {api.connected && (
              <Select
                aria-label="Active user profile"
                className="profile-selector"
                data={
                  snapshot?.profiles.map((p) => ({
                    value: p.id,
                    label: p.name,
                  })) || [{ value: profile, label: profileName }]
                }
                value={profile}
                onChange={(id) => {
                  if (hasEdits) setConfirm(() => () => api.chooseProfile(id));
                  else api.chooseProfile(id);
                }}
                leftSection={
                  <span className="profile-avatar">
                    {profileName.slice(0, 1).toUpperCase()}
                  </span>
                }
              />
            )}
            <span className="edition">LOCAL DASHBOARD</span>
          </Group>
        </header>
        <main className="page-wrap">
          {!snapshot && (
            <section className="connect-screen">
              <span className="welcome-icon">
                <Radio size={28} />
              </span>
              <Text className="eyebrow">A CLEARER VIEW OF HOME</Text>
              <h1>
                Your spaces.
                <br />
                In the moment.
              </h1>
              <p>
                Temperature, energy and the details that matter.
                <br />
                All your connected spaces, together.
              </p>
              <Paper className="connect-card" p="xl" withBorder>
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    api.connect(password);
                    setPassword("");
                  }}
                >
                  <Stack>
                    <PasswordInput
                      aria-label="Dashboard access token"
                      label="Dashboard access token"
                      placeholder="Enter your dashboard token"
                      value={password}
                      onChange={(e) => setPassword(e.currentTarget.value)}
                      autoComplete="off"
                      required
                    />
                    <Button
                      type="submit"
                      loading={api.loading}
                      rightSection={<ArrowUpRight size={17} />}
                    >
                      Connect to your home
                    </Button>
                    {api.error && <Alert color="red">{api.error}</Alert>}
                  </Stack>
                </form>
              </Paper>
              <Text size="xs" c="dimmed" mt="lg">
                Your token stays in this page’s memory.
              </Text>
              {api.connected && (
                <Button variant="subtle" mt="sm" onClick={api.disconnect}>
                  Disconnect
                </Button>
              )}
            </section>
          )}
          {snapshot && (
            <>
              <nav className="navigation" aria-label="Dashboard sections">
                <div className="location-navigation">
                  <button
                    className={
                      page === "all" || page === "editor" ? "selected" : ""
                    }
                    aria-current={page === "all" ? "page" : undefined}
                    onClick={() =>
                      hasEdits ? setConfirm(() => discard) : setPage("all")
                    }
                  >
                    <LayoutGrid size={16} />
                    All
                  </button>
                  {configuration.locations.map((l) => (
                    <button
                      key={l.id}
                      className={page === "location:" + l.id ? "selected" : ""}
                      aria-current={
                        page === "location:" + l.id ? "page" : undefined
                      }
                      onClick={() => {
                        const navigate = () => {
                          discard();
                          setPage("location:" + l.id);
                        };
                        if (hasEdits) setConfirm(() => navigate);
                        else setPage("location:" + l.id);
                      }}
                    >
                      {l.name}
                    </button>
                  ))}
                </div>
                <div className="utility-navigation">
                  <button
                    className={
                      page === "setup" ? "selected setup-tab" : "setup-tab"
                    }
                    aria-current={page === "setup" ? "page" : undefined}
                    onClick={() => {
                      const go = () => {
                        discard();
                        setPage("setup");
                      };
                      if (hasEdits) setConfirm(() => go);
                      else go();
                    }}
                  >
                    <SlidersHorizontal size={16} />
                    <span>Configuration & Setup</span>
                  </button>
                  <button
                    className={
                      page === "system" ? "selected setup-tab" : "setup-tab"
                    }
                    aria-current={page === "system" ? "page" : undefined}
                    onClick={() => {
                      const go = () => {
                        discard();
                        setPage("system");
                      };
                      if (hasEdits) setConfirm(() => go);
                      else go();
                    }}
                  >
                    <Database size={16} />
                    <span>System</span>
                  </button>
                </div>
              </nav>
              {api.error && (
                <Alert color="orange" mb="lg" title="Connection interrupted">
                  {api.error}. Showing last received readings; this page will
                  retry automatically.
                </Alert>
              )}
              {snapshot.state.gateway.gap && (
                <Alert color="orange" mb="lg">
                  A recording interruption was recorded. Missing measurements
                  have not been filled in.
                </Alert>
              )}
              {page === "all" && (
                <section id="all-overview" aria-label="All sensors">
                  <div className="overview-heading">
                    <div>
                      <h2>Live overview</h2>
                      <p>
                        Environmental sensors & energy · latest received values
                      </p>
                      <Button variant="light" mt="sm" onClick={begin}>
                        Edit layout
                      </Button>
                    </div>
                    <div className="overview-count">
                      <span>{String(devices.length).padStart(2, "0")}</span>
                      <p>
                        DISPLAYED
                        <br />
                        DEVICES
                      </p>
                    </div>
                  </div>
                  <div className="summary-strip">
                    <span>
                      <span className="live-dot" />
                      {devices.length - staleCount} devices with current
                      readings
                    </span>
                    <span>
                      {staleCount
                        ? `${staleCount} with missing, invalid or stale readings`
                        : "All supported readings within freshness windows"}
                    </span>
                    <span>
                      {devices.filter((d) => d.plug).length} metering plugs
                    </span>
                  </div>
                  {!devices.length ? (
                    <Paper p="xl" withBorder>
                      No supported devices discovered yet. Pair and discover
                      devices in the existing Setup dashboard.
                    </Paper>
                  ) : (
                    <Grid
                      key={`${profile}-${mode}-view`}
                      items={items}
                      columns={breakpoints[mode]}
                      renderTile={(id) => (
                        <Tile
                          device={devices.find((d) => d.ieee === id)}
                          locations={configuration.locations}
                          units={preferences.temperature_unit}
                          layout={draft || settings}
                          history={trendFor(id)}
                        />
                      )}
                    />
                  )}
                </section>
              )}
              {currentLocation && (
                <Location
                  onEditingChange={setLocationEditing}
                  key={profile + ":" + currentLocation.id}
                  location={currentLocation}
                  configuration={configuration}
                  devices={snapshot.devices}
                  fetched={snapshot.fetched}
                  request={api.request}
                  api={api}
                  online={online}
                  screen={screen}
                  renderDevice={(device) => (
                    <Tile
                      device={device}
                      locations={configuration.locations}
                      units={preferences.temperature_unit}
                      layout={draft || settings}
                    />
                  )}
                />
              )}
              {page === "setup" && (
                <React.Suspense fallback={<Text>Loading Setup…</Text>}>
                  <Setup api={api} online={online} onLayout={begin} />
                </React.Suspense>
              )}
              {page === "system" && (
                <React.Suspense
                  fallback={<Text>Loading System dashboard…</Text>}
                >
                  <SystemDashboard api={api} />
                </React.Suspense>
              )}
              {page === "editor" && draft && (
                <section className="layout-editor">
                  <div className="editor-heading">
                    <div>
                      <Text className="eyebrow">YOUR VIEW · {profileName}</Text>
                      <h2>Edit All dashboard</h2>
                      <p>
                        Drag using the grip, resize from a corner, or use the
                        numbered controls. Changes stay here until you save.
                      </p>
                    </div>
                    <Button
                      variant="subtle"
                      leftSection={<ArrowLeft size={16} />}
                      onClick={() => setConfirm(() => discard)}
                    >
                      Back to overview
                    </Button>
                  </div>
                  <Paper withBorder p="lg" className="editor-toolbar">
                    <div>
                      <Text size="sm" fw={600} mb={5}>
                        Screen layout
                      </Text>
                      <SegmentedControl
                        aria-label="Screen layout"
                        value={mode}
                        onChange={setEditScreen}
                        data={[
                          { value: "desktop", label: "Desktop" },
                          { value: "tablet", label: "Tablet" },
                          { value: "mobile", label: "Phone" },
                        ]}
                      />
                    </div>
                    <div>
                      <Text size="sm" fw={600} mb={5}>
                        Appearance
                      </Text>
                      <SegmentedControl
                        aria-label="Appearance"
                        value={draft.theme}
                        onChange={(theme) => setDraft((d) => ({ ...d, theme }))}
                        data={[
                          {
                            value: "light",
                            label: (
                              <Group gap={5}>
                                <Sun size={15} />
                                Light
                              </Group>
                            ),
                          },
                          {
                            value: "dark",
                            label: (
                              <Group gap={5}>
                                <Moon size={15} />
                                Dark
                              </Group>
                            ),
                          },
                        ]}
                      />
                    </div>
                    <Button
                      variant="default"
                      leftSection={<RotateCcw size={15} />}
                      onClick={() =>
                        setDraft((d) => ({
                          ...d,
                          all: { ...d.all, [mode]: [] },
                        }))
                      }
                    >
                      Reset this screen layout
                    </Button>
                  </Paper>
                  <Paper withBorder p="lg" className="accessible-editor">
                    <Select
                      label="Tile"
                      value={chosen?.id || null}
                      onChange={setSelected}
                      data={items.map((n) => ({
                        value: n.id,
                        label:
                          devices.find((d) => d.ieee === n.id)?.name || n.id,
                      }))}
                    />
                    {chosen &&
                      [
                        ["x", "Column", 0, breakpoints[mode] - chosen.w],
                        ["y", "Row", 0, 900],
                        ["w", "Width", 1, breakpoints[mode]],
                        ["h", "Height", 3, 20],
                      ].map(([key, label, min, max]) => (
                        <NumberInput
                          key={key}
                          label={label}
                          value={chosen[key]}
                          min={min}
                          max={max}
                          allowDecimal={false}
                          onChange={(value) => {
                            if (typeof value === "number")
                              change({ [key]: value });
                          }}
                        />
                      ))}
                    <Text size="xs" c="dimmed">
                      Columns and rows start at 0. Neighbouring tiles move down
                      to make room.
                    </Text>
                  </Paper>
                  {chosen && (
                    <AppearanceEditor
                      layout={draft}
                      kind="all"
                      id={chosen.id}
                      onChange={(presentation) =>
                        setDraft((d) => ({ ...d, presentation }))
                      }
                    />
                  )}
                  <Text size="sm" c="dimmed" mb="sm">
                    Editing {mode} · {breakpoints[mode]} column
                    {breakpoints[mode] > 1 ? "s" : ""}. Viewing a different
                    screen width never overwrites your saved layout.
                  </Text>
                  <Grid
                    key={`${profile}-${mode}-edit`}
                    items={items}
                    columns={breakpoints[mode]}
                    editing
                    onChange={updateItems}
                    renderTile={(id) => (
                      <Tile
                        device={devices.find((d) => d.ieee === id)}
                        locations={configuration.locations}
                        units={preferences.temperature_unit}
                        layout={draft || settings}
                        history={trendFor(id)}
                        editing
                      />
                    )}
                  />
                  {saveError && (
                    <Alert color="orange" title="Layout not saved" mt="md">
                      <Text size="sm">{saveError}</Text>
                      {saveError.startsWith("Configuration changed") && (
                        <Group mt="sm">
                          <Button
                            variant="default"
                            onClick={async () => {
                              try {
                                await api.reload();
                                discard();
                              } catch (e) {
                                setSaveError(e.message);
                              }
                            }}
                          >
                            Reload and discard edit
                          </Button>
                          <Button onClick={() => save(true)} loading={saving}>
                            Reapply layout to latest configuration
                          </Button>
                        </Group>
                      )}
                    </Alert>
                  )}
                  <div className="save-bar">
                    <Text size="sm">
                      Layout and theme · <strong>{profileName}</strong>
                    </Text>
                    <Group>
                      <Button
                        variant="default"
                        onClick={discard}
                        disabled={saving}
                      >
                        Discard changes
                      </Button>
                      <Button
                        leftSection={<Check size={17} />}
                        onClick={() => save()}
                        loading={saving}
                      >
                        Save layout
                      </Button>
                    </Group>
                  </div>
                </section>
              )}
              <footer className="page-footer">
                <span>
                  <Radio size={14} /> Local telemetry · recorded on your
                  Raspberry Pi.
                </span>
                <div>
                  <Text size="xs">
                    Last received data · signal is coordinator reception, not
                    mesh route
                  </Text>
                  <Button
                    variant="subtle"
                    size="compact-xs"
                    leftSection={<LogOut size={13} />}
                    onClick={() =>
                      hasEdits
                        ? setConfirm(() => api.disconnect)
                        : api.disconnect()
                    }
                  >
                    Disconnect
                  </Button>
                </div>
              </footer>
            </>
          )}
        </main>
        <Modal
          opened={!!confirm}
          onClose={() => setConfirm(null)}
          title="Leave this view?"
          centered
        >
          <Text size="sm" mb="lg">
            {hasEdits
              ? "Unsaved layout changes will be discarded."
              : "Continue to the selected view."}
          </Text>
          <Group justify="flex-end">
            <Button variant="default" onClick={() => setConfirm(null)}>
              Stay here
            </Button>
            <Button
              onClick={() => {
                const action = confirm;
                setConfirm(null);
                action?.();
              }}
            >
              Continue
            </Button>
          </Group>
        </Modal>
      </div>
    </MantineProvider>
  );
}

createRoot(document.getElementById("root")).render(<App />);
