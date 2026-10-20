import AppearanceEditor from "./AppearanceEditor.jsx";
import {
  presentationCSS,
  seriesColor,
  mergePresentation,
  emptyPresentation,
} from "./presentation.js";
import Grid from "./Grid.jsx";
import ConfigForm from "./ConfigForm.jsx";
import PlugControls from "./PlugControls.jsx";
import WidgetEditor, {
  ranges,
  sources,
  sourceKey,
  nextId,
} from "./WidgetEditor.jsx";
import { useAction, Feedback } from "./actions.jsx";
import {
  widgetLayout,
  emptyLayout,
  breakpoints,
  mergePresent,
  editItem,
} from "./layout.js";
import { useEffect, useRef, useState } from "react";
import {
  Paper,
  Text,
  Alert,
  Badge,
  Button,
  Group,
  Select,
  NumberInput,
  SegmentedControl,
} from "@mantine/core";
import { Signal, ChartNoAxesCombined, Grip } from "lucide-react";
import { age, quality, display } from "./layout.js";
import { areaPath, geometry, historyKey, measurementFor } from "./history.js";

export function useHistories(widgets, devices, request, fetched) {
  const [visible, setVisible] = useState(() => !document.hidden);
  useEffect(() => {
    const update = () => setVisible(!document.hidden);
    document.addEventListener("visibilitychange", update);
    return () => document.removeEventListener("visibilitychange", update);
  }, []);
  const [data, setData] = useState({}),
    cache = useRef(new Map()),
    jobs = useRef(new Map()),
    queue = useRef([]),
    running = useRef(0),
    disposed = useRef(false);
  useEffect(() => {
    disposed.current = false;
    return () => {
      disposed.current = true;
      for (const job of jobs.current.values()) job.controller.abort();
      jobs.current.clear();
      queue.current = [];
    };
  }, []);
  useEffect(() => {
    if (!visible) {
      for (const job of jobs.current.values()) job.controller.abort();
      jobs.current.clear();
      queue.current = [];
      return;
    }
    const charts = new Map(
      widgets.filter((w) => w.type === "chart").map((w) => [historyKey(w), w]),
    );
    for (const key of cache.current.keys())
      if (!charts.has(key)) cache.current.delete(key);
    setData((old) => {
      const keys = Object.keys(old);
      return keys.some((key) => !charts.has(key))
        ? Object.fromEntries(
            Object.entries(old).filter(([key]) => charts.has(key)),
          )
        : old;
    });
    for (const [key, job] of jobs.current)
      if (!charts.has(key)) {
        job.controller.abort();
        jobs.current.delete(key);
      }
    for (const [key, w] of charts) {
      const latest =
        measurementFor(
          devices.find((d) => d.ieee === w.source.ieee),
          w.source,
        )?.received_at || 0;
      const saved = cache.current.get(key);
      if (
        jobs.current.has(key) ||
        (saved &&
          (Date.now() - saved.loadedAt < (w.sparkline ? 60000 : 30000) ||
            (saved.latest === latest && Date.now() - saved.loadedAt < 60000)))
      )
        continue;
      const job = { key, widget: w, latest, controller: new AbortController() };
      jobs.current.set(key, job);
      queue.current.push(job);
    }
    const pump = () => {
      while (!disposed.current && running.current < 2 && queue.current.length) {
        const job = queue.current.shift();
        if (job.controller.signal.aborted) continue;
        running.current++;
        (async () => {
          const to = Date.now() / 1000,
            from = to - job.widget.time_range;
          let result;
          try {
            const params = new URLSearchParams({
              ...job.widget.source,
              from,
              to,
              limit: job.widget.sparkline ? 120 : 500,
            });
            let items = [],
              gaps = [],
              cursor = null,
              pages = 0,
              gapsTruncated = false;
            do {
              if (cursor) params.set("cursor", cursor);
              const response = await request("/api/v2/history?" + params, {
                signal: job.controller.signal,
              });
              items.push(...response.data.items);
              gaps = response.data.gaps;
              gapsTruncated = response.data.gaps_truncated;
              cursor = response.data.next_cursor;
              pages++;
            } while (cursor && pages < (job.widget.sparkline ? 1 : 20));
            result = {
              items,
              gaps,
              gapsTruncated,
              truncated: !!cursor,
              from,
              to,
            };
          } catch (e) {
            if (e.name !== "AbortError") result = { error: e.message };
          } finally {
            running.current--;
            if (jobs.current.get(job.key) === job) jobs.current.delete(job.key);
            if (!disposed.current && !job.controller.signal.aborted && result) {
              const entry = {
                ...result,
                loadedAt: Date.now(),
                latest: job.latest,
              };
              cache.current.set(job.key, entry);
              setData((old) => ({ ...old, [job.key]: entry }));
            }
            pump();
          }
        })();
      }
    };
    pump();
  }, [widgets, devices, request, fetched, visible]);
  return data;
}
function Chart({ widget, data, unit, units }) {
  const [selection, setSelection] = useState(null);
  if (!data)
    return <p className="chart-message">Loading measurement history…</p>;
  if (data.error)
    return (
      <Alert color="orange" mt="md">
        History unavailable: {data.error}
      </Alert>
    );
  const plot = geometry(
    data,
    units === "fahrenheit",
    widget.source.cluster === 6,
  );
  if (!plot)
    return (
      <p className="chart-message">
        No valid readings in this time range. Missing data is not zero.
      </p>
    );
  const current = Math.min(
      selection ?? plot.valid.length - 1,
      plot.valid.length - 1,
    ),
    point = plot.valid[current];
  const label = (time) =>
    new Date(time * 1000).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  return (
    <div className="history-chart">
      <div className="chart-headline">
        <span className="metric-reading">
          {display(plot.valid.at(-1), units).value}
        </span>
        <small>{unit}</small>
        <Text size="xs" c="dimmed">
          Last in range
        </Text>
      </div>
      <svg
        viewBox="0 0 560 220"
        role="img"
        tabIndex={0}
        aria-label={`${widget.title} history. Use left and right arrows to inspect readings.`}
        onKeyDown={(e) => {
          if (e.key === "ArrowLeft" || e.key === "ArrowRight") {
            e.preventDefault();
            setSelection(
              Math.max(
                0,
                Math.min(
                  plot.valid.length - 1,
                  current + (e.key === "ArrowLeft" ? -1 : 1),
                ),
              ),
            );
          }
        }}
        onPointerMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect(),
            fraction = Math.max(
              0,
              Math.min(
                1,
                (((e.clientX - rect.left) / rect.width) * 560 - 52) / 488,
              ),
            ),
            target = data.from + fraction * (data.to - data.from);
          let nearest = 0;
          for (let i = 1; i < plot.valid.length; i++)
            if (
              Math.abs(plot.valid[i].received_at - target) <
              Math.abs(plot.valid[nearest].received_at - target)
            )
              nearest = i;
          setSelection(nearest);
        }}
      >
        {(widget.source.cluster === 6
          ? [0, 1]
          : [plot.low, (plot.low + plot.high) / 2, plot.high]
        ).map((value) => (
          <g key={value}>
            <line
              x1="52"
              x2="540"
              y1={plot.y(value)}
              y2={plot.y(value)}
              className="history-axis"
            />
            <text x="44" y={plot.y(value) + 4} textAnchor="end">
              {widget.source.cluster === 6
                ? value
                  ? "On"
                  : "Off"
                : value.toLocaleString(undefined, { maximumFractionDigits: 1 })}
            </text>
          </g>
        ))}
        {data.gaps.map((g, i) => (
          <rect
            key={i}
            x={plot.x(Math.max(data.from, g.from))}
            y="24"
            width={Math.max(
              2,
              plot.x(Math.min(data.to, g.to)) -
                plot.x(Math.max(data.from, g.from)),
            )}
            height="156"
            className="history-gap"
          >
            <title>
              Recording interruption: {g.reason.replaceAll("_", " ")}
            </title>
          </rect>
        ))}
        <path d={areaPath(plot.path)} className="history-area" />
        <path d={plot.path} className="history-line" />
        <circle
          cx={plot.x(point.received_at)}
          cy={plot.y(plot.number(point))}
          r="3.5"
          className="history-point"
        />
        <text x="52" y="207">
          {label(data.from)}
        </text>
        <text x="540" y="207" textAnchor="end">
          {label(data.to)}
        </text>
        <text x="52" y="13">
          {unit}
        </text>
      </svg>
      <div className="history-summary">
        {[
          ["Min", Math.min(...plot.valid.map(plot.number))],
          ["Max", Math.max(...plot.valid.map(plot.number))],
        ].map(([name, value]) => (
          <span key={name}>
            {name}{" "}
            <strong>
              {value.toLocaleString(undefined, { maximumFractionDigits: 2 })}{" "}
              {unit}
            </strong>
          </span>
        ))}
        <span>{plot.valid.length} recorded samples · selected period</span>
      </div>
      <p className="chart-inspection">
        {label(point.received_at)} ·{" "}
        <strong>
          {display(point, units).value} {display(point, units).unit}
        </strong>
      </p>
      {!!data.gaps.length && (
        <p className="history-warning">
          Shading marks known recording interruptions; lines do not bridge gaps.
        </p>
      )}
      {(data.truncated || data.gapsTruncated) && (
        <p className="history-warning">
          History response reached its display limit. Some readings or gap
          annotations are omitted.
        </p>
      )}
    </div>
  );
}
function LocationWidget({
  widget: w,
  device,
  history,
  units,
  editing,
  onEdit,
  onRemove,
  onMove,
  onRange,
  disabled,
  first,
  last,
  layout,
}) {
  const measurement = measurementFor(device, w.source),
    value = display(measurement || { value: null, unit: "" }, units),
    q = measurement ? quality(measurement) : "missing";
  return (
    <Paper
      withBorder
      className={`location-widget ${w.type === "chart" ? "chart-widget" : ""}`}
      p="lg"
      style={{
        ...presentationCSS(layout, "widgets", w.id),
        "--series-color": seriesColor(w.source.cluster, w.source.attribute),
      }}
    >
      <div className="location-widget-heading">
        <div>
          <p className="location-label">
            {device?.name || "Unavailable device"} · EP {w.source.endpoint}
          </p>
          <h3>{w.title}</h3>
        </div>
        {editing ? (
          <span className="tile-handle" aria-hidden="true">
            <Grip size={20} />
          </span>
        ) : (
          w.type === "chart" && <ChartNoAxesCombined size={19} />
        )}
      </div>
      {w.type === "chart" ? (
        <>
          <Text size="xs" c="dimmed">
            {ranges.find((r) => r.value === String(w.time_range))?.label}
          </Text>
          <Chart widget={w} data={history} unit={value.unit} units={units} />
        </>
      ) : (
        <div className="location-numeric">
          <span className="metric-reading">{value.value}</span>
          <small>{value.unit}</small>
        </div>
      )}
      <p className={q !== "valid" ? "history-warning" : "measurement-age"}>
        {q !== "valid"
          ? `${q === "missing" ? "No reading" : q === "invalid" ? "Invalid reading" : "Stale"} · `
          : ""}
        {age(measurement?.received_at)}
        {measurement?.origin
          ? " · " + measurement.origin.replaceAll("_", " ")
          : ""}
        {measurement?.low_battery ? " · Low battery" : ""}
      </p>
      {!editing && (
        <div className="widget-controls">
          <Group gap="xs">
            <Button size="compact-xs" variant="subtle" onClick={onEdit}>
              Edit
            </Button>
            <Button
              size="compact-xs"
              variant="subtle"
              aria-label={"Move " + w.title + " up"}
              disabled={disabled || first}
              onClick={() => onMove(-1)}
            >
              ↑
            </Button>
            <Button
              size="compact-xs"
              variant="subtle"
              aria-label={"Move " + w.title + " down"}
              disabled={disabled || last}
              onClick={() => onMove(1)}
            >
              ↓
            </Button>
            <Button
              size="compact-xs"
              variant="subtle"
              color="red"
              disabled={disabled}
              onClick={onRemove}
            >
              Remove
            </Button>
          </Group>
          {w.type === "chart" && (
            <Select
              aria-label={"Time range for " + w.title}
              size="xs"
              value={String(w.time_range)}
              data={ranges}
              disabled={disabled}
              onChange={(value) => onRange(Number(value))}
            />
          )}
        </div>
      )}
    </Paper>
  );
}
function Arrange({ api, location, widgets, screen, renderWidget, onClose }) {
  const [mode, setMode] = useState(screen),
    [selected, setSelected] = useState(widgets[0]?.id || "");
  return (
    <ConfigForm
      api={api}
      configuration={api.snapshot.configuration}
      label="Save location layout"
      onSaved={onClose}
      initial={(c) => ({
        presentationBase: structuredClone(
          c.dashboard.grid_layout?.presentation || emptyPresentation(),
        ),
        presentation: structuredClone(
          c.dashboard.grid_layout?.presentation || emptyPresentation(),
        ),
        layoutBase: structuredClone(
          c.dashboard.grid_layout?.locations?.[location.id] || {
            desktop: [],
            tablet: [],
            mobile: [],
          },
        ),
        layout: structuredClone(
          c.dashboard.grid_layout?.locations?.[location.id] || {
            desktop: [],
            tablet: [],
            mobile: [],
          },
        ),
      })}
      apply={(c, v) => {
        c.dashboard.grid_layout ||= emptyLayout();
        c.dashboard.grid_layout.locations ||= {};
        if (!c.locations.some((l) => l.id === location.id))
          throw Error("Location removed in another session.");
        const current = c.dashboard.grid_layout.locations[location.id] || {
          desktop: [],
          tablet: [],
          mobile: [],
        };
        c.dashboard.grid_layout.locations[location.id] = Object.fromEntries(
          Object.keys(breakpoints).map((key) => [
            key,
            JSON.stringify(v.layoutBase[key]) === JSON.stringify(v.layout[key])
              ? current[key]
              : v.layout[key],
          ]),
        );
        c.dashboard.grid_layout.presentation = mergePresentation(
          c.dashboard.grid_layout.presentation,
          v.presentationBase,
          v.presentation,
        );
      }}
    >
      {(v, set) => {
        const nodes = widgetLayout(widgets, v.layout, mode),
          chosen = nodes.find((n) => n.id === selected) || nodes[0];
        const change = (items) =>
          set("layout", {
            ...v.layout,
            [mode]: mergePresent(v.layout[mode], items),
          });
        return (
          <>
            <Group mb="md">
              <SegmentedControl
                value={mode}
                onChange={setMode}
                data={[
                  { value: "desktop", label: "Desktop" },
                  { value: "tablet", label: "Tablet" },
                  { value: "mobile", label: "Phone" },
                ]}
              />
              <Button
                variant="default"
                onClick={() => set("layout", { ...v.layout, [mode]: [] })}
              >
                Reset this screen layout
              </Button>
              <Button variant="subtle" onClick={onClose}>
                Discard layout edits
              </Button>
            </Group>
            <Paper withBorder p="lg" className="accessible-editor">
              <Select
                label="Widget"
                value={chosen?.id || null}
                onChange={setSelected}
                data={widgets.map((w) => ({ value: w.id, label: w.title }))}
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
                        change(
                          editItem(
                            nodes,
                            chosen.id,
                            { [key]: value },
                            breakpoints[mode],
                          ),
                        );
                    }}
                  />
                ))}
            </Paper>
            {chosen && (
              <AppearanceEditor
                layout={{
                  ...api.snapshot.configuration.data.dashboard.grid_layout,
                  presentation: v.presentation,
                }}
                kind="widgets"
                id={chosen.id}
                onChange={(p) => set("presentation", p)}
              />
            )}
            <Text size="sm" c="dimmed" mb="sm">
              Editing {mode} layout. Drag by the grip or use the numbered
              controls. Changes are saved only when requested.
            </Text>
            <Grid
              key={mode + "-edit"}
              items={nodes}
              columns={breakpoints[mode]}
              editing
              onChange={change}
              renderTile={(id) => {
                const w = widgets.find((w) => w.id === id);
                return w
                  ? renderWidget(w, true, {
                      ...api.snapshot.configuration.data.dashboard.grid_layout,
                      presentation: v.presentation,
                    })
                  : null;
              }}
            />
          </>
        );
      }}
    </ConfigForm>
  );
}
export default function Location({
  location,
  configuration,
  devices,
  fetched,
  request,
  renderDevice,
  api,
  online,
  screen,
  onEditingChange,
}) {
  const members = devices.filter((d) => d.location_id === location.id),
    [editor, setEditor] = useState(null),
    [arranging, setArranging] = useState(false),
    action = useAction(request);
  useEffect(() => {
    onEditingChange?.(arranging);
    return () => onEditingChange?.(false);
  }, [arranging, onEditingChange]);
  const widgets = configuration.dashboard.widgets
    .filter(
      (w) => configuration.devices[w.source.ieee]?.location_id === location.id,
    )
    .sort((a, b) => a.position - b.position);
  const histories = useHistories(widgets, devices, request, fetched),
    units = configuration.dashboard.temperature_unit;
  const choices = sources(devices, location.id);
  const mutate = (fn) => action.perform(() => api.updateConfiguration(fn));
  const renderWidget = (
    w,
    editing = false,
    layout = configuration.dashboard.grid_layout,
  ) => {
    const index = widgets.findIndex((item) => item.id === w.id);
    return (
      <LocationWidget
        widget={w}
        layout={layout}
        device={devices.find((d) => d.ieee === w.source.ieee)}
        history={histories[historyKey(w)]}
        units={units}
        editing={editing}
        disabled={action.busy}
        first={
          index === 0 ||
          !!configuration.dashboard.grid_layout?.locations?.[location.id]?.[
            screen
          ]?.length
        }
        last={
          index === widgets.length - 1 ||
          !!configuration.dashboard.grid_layout?.locations?.[location.id]?.[
            screen
          ]?.length
        }
        onEdit={() => setEditor(w)}
        onRemove={() =>
          mutate((c) => {
            c.dashboard.widgets = c.dashboard.widgets.filter(
              (v) => v.id !== w.id,
            );
            if (c.dashboard.grid_layout?.locations?.[location.id])
              for (const key of Object.keys(breakpoints))
                c.dashboard.grid_layout.locations[location.id][key] =
                  c.dashboard.grid_layout.locations[location.id][key].filter(
                    (n) => n.id !== w.id,
                  );
          })
        }
        onMove={(direction) =>
          mutate((c) => {
            const a = c.dashboard.widgets.find((v) => v.id === w.id),
              b = c.dashboard.widgets.find(
                (v) => v.id === widgets[index + direction]?.id,
              );
            if (!a || !b) throw Error("Widget order changed.");
            [a.position, b.position] = [b.position, a.position];
          })
        }
        onRange={(range) =>
          mutate((c) => {
            const item = c.dashboard.widgets.find((v) => v.id === w.id);
            if (!item) throw Error("Widget removed.");
            item.time_range = range;
          })
        }
      />
    );
  };
  return (
    <section id="location-overview" aria-label={location.name}>
      <div className="overview-heading">
        <div>
          <h2>{location.name}</h2>
          <p>
            {members.length} device{members.length === 1 ? "" : "s"} · Latest
            readings and history
          </p>
        </div>
        <Group>
          <Badge variant="light" color="teal">
            {widgets.length} saved widgets
          </Badge>
          <Button
            variant="default"
            disabled={!choices.length || arranging}
            onClick={() => setEditor({ new: true })}
          >
            Add widget
          </Button>
          <Button
            variant="light"
            disabled={!widgets.length || arranging}
            onClick={() => setArranging(true)}
          >
            Edit layout
          </Button>
          <Button
            variant="subtle"
            disabled={!choices.length || action.busy || arranging}
            onClick={() =>
              mutate((c) => {
                for (const choice of choices.filter(
                  (o) => o.source.cluster !== 65535,
                ))
                  for (const type of ["numeric", "chart"]) {
                    if (
                      c.dashboard.widgets.some(
                        (w) =>
                          w.type === type &&
                          sourceKey(w.source) === sourceKey(choice.source),
                      )
                    )
                      continue;
                    const used = new Set(
                      c.dashboard.widgets.map((w) => w.position),
                    );
                    let position = 0;
                    while (used.has(position)) position++;
                    c.dashboard.widgets.push({
                      id: nextId(),
                      title:
                        choice.title + (type === "chart" ? " history" : ""),
                      type,
                      source: choice.source,
                      time_range: 86400,
                      position,
                    });
                  }
              })
            }
          >
            Add sensor widgets
          </Button>
        </Group>
      </div>
      <div className="location-signal-strip">
        {members.map((d) => (
          <span key={d.ieee}>
            <Signal size={14} />
            {d.name} ·{" "}
            {d.signal?.value == null
              ? "Signal not received"
              : `${d.signal.value} dBm · ${quality(d.signal) === "stale" ? "Stale · " : ""}${age(d.signal.received_at)}`}
          </span>
        ))}
      </div>
      {!!members.filter((d) => d.plug).length && (
        <section
          className="plug-controls-section"
          aria-label="Smart plug controls"
        >
          <Text fw={600} mb="xs">
            Plug switches
          </Text>
          <Text size="xs" c="dimmed" mb="sm">
            Gateway-reported state is authoritative.
          </Text>
          <div className="plug-toggle-board">
            {members
              .filter((d) => d.plug)
              .map((d) => (
                <PlugControls
                  key={d.ieee}
                  device={d}
                  request={request}
                  gateway={api.snapshot.state.gateway}
                  online={online}
                  compact
                  variant="toggle"
                />
              ))}
          </div>
        </section>
      )}
      {!!members.filter((d) => d.plug).length && (
        <section
          className="plug-operation-section"
          aria-label="Plug operation outputs"
        >
          <Text fw={600} mb="xs">
            Plug operation
          </Text>
          <div className="plug-operations-grid">
            {members
              .filter((d) => d.plug)
              .map((d) => (
                <PlugControls
                  key={d.ieee}
                  device={d}
                  request={request}
                  gateway={api.snapshot.state.gateway}
                  online={online}
                  compact
                  variant="operation"
                />
              ))}
          </div>
        </section>
      )}
      <Feedback action={action} />
      {!members.length && (
        <Paper p="xl" withBorder>
          No devices assigned to this location yet.
        </Paper>
      )}
      {!!members.length && !widgets.length && (
        <>
          <Text size="sm" c="dimmed" mb="lg">
            No saved widgets in this profile. Showing current device readings.
          </Text>
          <div className="location-device-grid">
            {members.map((d) => (
              <div key={d.ieee}>{renderDevice(d)}</div>
            ))}
          </div>
        </>
      )}
      {!!widgets.length &&
        (arranging ? (
          <Arrange
            api={api}
            location={location}
            widgets={widgets}
            screen={screen}
            renderWidget={renderWidget}
            onClose={() => setArranging(false)}
          />
        ) : (
          <Grid
            key={screen + "-view"}
            items={widgetLayout(
              widgets,
              configuration.dashboard.grid_layout?.locations?.[location.id],
              screen,
            )}
            columns={breakpoints[screen]}
            renderTile={(id) => {
              const w = widgets.find((w) => w.id === id);
              return w ? renderWidget(w) : null;
            }}
          />
        ))}
      {editor && (
        <WidgetEditor
          api={api}
          location={location.id}
          widget={editor.new ? null : editor}
          onClose={() => setEditor(null)}
        />
      )}
    </section>
  );
}
