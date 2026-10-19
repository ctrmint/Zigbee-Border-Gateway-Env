import { Modal, Select, Stack, TextInput } from "@mantine/core";
import ConfigForm from "./ConfigForm.jsx";
export const ranges = [
  { value: "3600", label: "Last hour" },
  { value: "21600", label: "Last 6 hours" },
  { value: "86400", label: "Last 24 hours" },
  { value: "604800", label: "Last 7 days" },
  { value: "2592000", label: "Last 30 days" },
];
export const sourceKey = (s) =>
  [s.ieee, s.endpoint, s.cluster, s.attribute].join(":");
export function sources(devices, location) {
  return devices
    .filter((d) => d.location_id === location)
    .flatMap((d) =>
      [...d.measurements, ...(d.signal ? [d.signal] : [])].map((m) => ({
        source: {
          ieee: d.ieee,
          endpoint: m.endpoint,
          cluster: m.cluster,
          attribute: m.attribute,
        },
        label: `${d.name} · EP ${m.endpoint} · ${m.label}`,
        title: m.label,
      })),
    );
}
export function nextId() {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return (
    "w-" + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("")
  );
}
export default function WidgetEditor({ api, location, widget, onClose }) {
  const choices = sources(api.snapshot.devices, location);
  if (!choices.length)
    return (
      <Modal opened onClose={onClose} title="No available measurements">
        Discover device endpoints first.
      </Modal>
    );
  return (
    <Modal
      opened
      onClose={onClose}
      title={widget ? "Edit widget" : "Add widget"}
      centered
    >
      <ConfigForm
        api={api}
        configuration={api.snapshot.configuration}
        label="Save widget"
        onSaved={onClose}
        initial={() => ({
          title: widget?.title || choices[0].title,
          type: widget?.type || "numeric",
          source: sourceKey(widget?.source || choices[0].source),
          range: String(widget?.time_range || 86400),
        })}
        apply={(c, v) => {
          const selected = choices.find(
            (o) => sourceKey(o.source) === v.source,
          );
          if (!selected) throw Error("Select an available source.");
          const current =
            widget && c.dashboard.widgets.find((w) => w.id === widget.id);
          if (widget && !current) throw Error("Widget was removed elsewhere.");
          const used = new Set(c.dashboard.widgets.map((w) => w.position));
          let position = 0;
          while (used.has(position)) position++;
          const value = {
            id: widget?.id || nextId(),
            title: v.title,
            type: v.type,
            source: selected.source,
            time_range: Number(v.range),
            position: current?.position ?? position,
          };
          if (current)
            c.dashboard.widgets = c.dashboard.widgets.map((w) =>
              w.id === value.id ? value : w,
            );
          else c.dashboard.widgets.push(value);
        }}
      >
        {(v, set) => (
          <Stack>
            <TextInput
              label="Widget title"
              aria-label="Widget title"
              maxLength={80}
              value={v.title}
              required
              onChange={(e) => set("title", e.currentTarget.value)}
            />
            <Select
              label="Display"
              value={v.type}
              data={[
                { value: "numeric", label: "Numeric instant reading" },
                { value: "chart", label: "History chart" },
              ]}
              onChange={(value) => set("type", value)}
            />
            <Select
              label="Device endpoint measurement"
              value={v.source}
              data={choices.map((o) => ({
                value: sourceKey(o.source),
                label: o.label,
              }))}
              onChange={(value) => set("source", value)}
            />
            <Select
              label="Chart time range"
              value={v.range}
              data={ranges}
              onChange={(value) => set("range", value)}
            />
          </Stack>
        )}
      </ConfigForm>
    </Modal>
  );
}
