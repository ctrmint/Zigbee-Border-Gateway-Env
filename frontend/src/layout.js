import { mergePresentation } from "./presentation.js";
export const breakpoints = { desktop: 12, tablet: 6, mobile: 1 };
export const emptyLayout = () => ({
  version: 1,
  theme: "dark",
  all: { desktop: [], tablet: [], mobile: [] },
  locations: {},
});
export const breakpointFor = (width) =>
  width < 700 ? "mobile" : width < 1100 ? "tablet" : "desktop";
export function eligible(devices, raw = []) {
  return devices.filter(
    (d) =>
      d.registered &&
      (d.plug ||
        d.measurements.some((m) => m.cluster !== 6) ||
        d.profile?.startsWith("SONOFF SNZB-02") ||
        Object.values(raw.find((r) => r.ieee === d.ieee)?.endpoints || {}).some(
          (ep) =>
            ep.device_id === 770 ||
            ep.input_clusters?.some((c) => c === 1026 || c === 1029),
        )),
  );
}
export function ordered(devices, legacy) {
  const rank = (id) => {
    const i = (legacy.order || []).indexOf(id);
    return i < 0 ? Infinity : i;
  };
  return [...devices].sort(
    (a, b) => rank(a.ieee) - rank(b.ieee) || a.ieee.localeCompare(b.ieee),
  );
}
export function effectiveLayout(devices, settings, legacy, breakpoint) {
  const cols = breakpoints[breakpoint],
    saved = settings.all[breakpoint];
  const ids = new Set(devices.map((d) => d.ieee));
  const result = saved.filter((n) => ids.has(n.id)).map((n) => ({ ...n }));
  // Saved absent devices retain their own position in storage, but don't reserve screen space.
  const present = new Set(result.map((n) => n.id));
  const minimum = legacy.min_tile_width || 240;
  const count =
    breakpoint === "mobile"
      ? 1
      : Math.min(
          cols,
          legacy.columns || (breakpoint === "tablet" ? 2 : 3),
          Math.max(
            1,
            Math.floor((breakpoint === "tablet" ? 900 : 1300) / minimum),
          ),
        );
  const w = Math.max(1, Math.floor(cols / count));
  for (const d of ordered(devices, legacy))
    if (!present.has(d.ieee)) {
      const n = {
        id: d.ieee,
        x: 0,
        y: 0,
        w,
        h: d.plug ? 7 : Math.max(4, Math.ceil(d.measurements.length / 2) + 2),
      };
      n.h = Math.min(20, n.h);
      while (result.some((a) => overlaps(n, a))) {
        n.x += w;
        if (n.x + w > cols) {
          n.x = 0;
          n.y++;
        }
      }
      result.push(n);
    }
  return result.sort(
    (a, b) => a.y - b.y || a.x - b.x || a.id.localeCompare(b.id),
  );
}
export const overlaps = (a, b) =>
  a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;
export function serializeGridItems(elements) {
  return elements.flatMap((element) => {
    const node = element.gridstackNode || {};
    const id =
      node.id || element.dataset?.sensorId || element.getAttribute?.("gs-id");
    if (!id) return [];
    const coordinate = (value, attribute, fallback) => {
      if (Number.isInteger(value)) return value;
      const raw = element.getAttribute?.(attribute);
      if (raw === null || raw === undefined) return fallback;
      const parsed = Number(raw);
      return Number.isInteger(parsed) ? parsed : fallback;
    };
    return [
      {
        id,
        x: coordinate(node.x, "gs-x", 0),
        y: coordinate(node.y, "gs-y", 0),
        w: coordinate(node.w, "gs-w", 1),
        h: coordinate(node.h, "gs-h", 1),
      },
    ];
  });
}
export function mergePresent(saved, current) {
  const present = new Set(current.map((n) => n.id));
  // Retain absent tiles below the edited surface to prevent overlapping saved rectangles.
  let bottom = Math.max(0, ...current.map((n) => n.y + n.h));
  return [
    ...current,
    ...saved
      .filter((n) => !present.has(n.id))
      .map((n) => {
        const moved = { ...n, y: bottom };
        bottom += n.h;
        return moved;
      }),
  ];
}
export function editItem(items, id, patch, columns) {
  const changed = items.map((n) =>
    n.id === id ? { ...n, ...patch } : { ...n },
  );
  const item = changed.find((n) => n.id === id);
  if (!item) return changed;
  item.w = Math.max(1, Math.min(columns, item.w));
  item.x = Math.max(0, Math.min(columns - item.w, item.x));
  item.y = Math.max(0, Math.min(900, item.y));
  item.h = Math.max(3, Math.min(20, item.h));
  // Explicit editor changes push colliding neighbours down, keeping the chosen position.
  const placed = [item];
  for (const n of changed
    .filter((n) => n.id !== id)
    .sort((a, b) => a.y - b.y || a.x - b.x)) {
    while (placed.some((p) => overlaps(p, n))) n.y++;
    placed.push(n);
  }
  return placed;
}
export function quality(m, now = Date.now() / 1000) {
  if (m.quality === "missing" || m.value === null || m.value === undefined)
    return m.quality === "missing" ? "missing" : "invalid";
  return m.received_at && now - m.received_at > (m.freshness_seconds || 3600)
    ? "stale"
    : m.quality;
}
export function age(time, now = Date.now() / 1000) {
  if (!time) return "No reading";
  const seconds = Math.max(0, Math.floor(now - time));
  return seconds < 60
    ? "Just received"
    : seconds < 3600
      ? `${Math.floor(seconds / 60)}m ago`
      : seconds < 86400
        ? `${Math.floor(seconds / 3600)}h ago`
        : `${Math.floor(seconds / 86400)}d ago`;
}
export function display(m, preference = "celsius") {
  if (m.value === null || m.value === undefined)
    return { value: "—", unit: m.unit === "on/off" ? "" : m.unit };
  const fahrenheit = m.unit === "°C" && preference === "fahrenheit";
  return {
    value:
      typeof m.value === "boolean"
        ? m.value
          ? "On"
          : "Off"
        : Number(fahrenheit ? (m.value * 9) / 5 + 32 : m.value).toLocaleString(
            undefined,
            { maximumFractionDigits: ["A", "kWh"].includes(m.unit) ? 3 : 2 },
          ),
    unit: fahrenheit ? "°F" : m.unit === "on/off" ? "" : m.unit,
  };
}

export function widgetLayout(widgets, saved, breakpoint) {
  const cols = breakpoints[breakpoint],
    ids = new Set(widgets.map((w) => w.id));
  const result = (saved?.[breakpoint] || [])
    .filter((n) => ids.has(n.id))
    .map((n) => ({ ...n }));
  for (const w of [...widgets].sort((a, b) => a.position - b.position))
    if (!result.some((n) => n.id === w.id)) {
      const n = {
        id: w.id,
        x: 0,
        y: 0,
        w: breakpoint === "mobile" ? 1 : cols / 2,
        h: w.type === "chart" ? 8 : 4,
      };
      while (result.some((a) => overlaps(n, a))) {
        n.x += n.w;
        if (n.x + n.w > cols) {
          n.x = 0;
          n.y++;
        }
      }
      result.push(n);
    }
  return result;
}

export function mergeAllLayout(current, edited, before) {
  return {
    ...(current || emptyLayout()),
    all: before
      ? Object.fromEntries(
          Object.keys(breakpoints).map((key) => [
            key,
            JSON.stringify(before.all?.[key] || []) ===
            JSON.stringify(edited.all[key])
              ? current?.all?.[key] || []
              : edited.all[key],
          ]),
        )
      : edited.all,
    theme:
      before && before.theme === edited.theme ? current.theme : edited.theme,
    ...(edited.presentation
      ? {
          presentation: mergePresentation(
            current?.presentation,
            before?.presentation,
            edited.presentation,
          ),
        }
      : {}),
  };
}
