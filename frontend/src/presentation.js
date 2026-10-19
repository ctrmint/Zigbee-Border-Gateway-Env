export const fonts = {
  system: 'system-ui, -apple-system, "Segoe UI", sans-serif',
  mono: 'ui-monospace, "SFMono-Regular", Consolas, "Liberation Mono", monospace',
  serif: 'Georgia, "Times New Roman", serif',
  rounded: 'ui-rounded, "Arial Rounded MT Bold", system-ui, sans-serif',
};
export const emptyPresentation = () => ({
  version: 1,
  defaults: {},
  all: {},
  widgets: {},
});
export function metricStyle(layout, kind, id) {
  const p = layout?.presentation || emptyPresentation();
  return {
    scale: 100,
    size: 44,
    font: "system",
    color: "auto",
    trend: true,
    ...p.defaults,
    ...p[kind]?.[id],
  };
}
export const seriesColor = (cluster, attribute = 0) =>
  cluster === 1026
    ? "var(--series-temperature)"
    : cluster === 1029
      ? "var(--series-humidity)"
      : cluster === 1
        ? "var(--series-violet)"
        : cluster === 65535
          ? "var(--series-green)"
          : [
              "var(--series-green)",
              "var(--series-humidity)",
              "var(--series-violet)",
              "var(--series-temperature)",
            ][attribute % 4];
export function presentationCSS(layout, kind, id) {
  const s = metricStyle(layout, kind, id);
  return {
    "--content-scale": s.scale / 100,
    "--metric-size": `${s.size}px`,
    "--metric-font": fonts[s.font],
    "--metric-color": s.color === "auto" ? undefined : s.color,
  };
}
export function contrast(a, b) {
  const luminance = (hex) => {
    const rgb = hex
      .match(/[a-f\d]{2}/gi)
      .map((v) => parseInt(v, 16) / 255)
      .map((v) => (v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
    return rgb[0] * 0.2126 + rgb[1] * 0.7152 + rgb[2] * 0.0722;
  };
  const x = luminance(a),
    y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}
// Merge only fields changed by this editor so reapply retains unrelated concurrent edits.
export function mergePresentation(current, before, edited) {
  const out = structuredClone(current || emptyPresentation());
  function mergeFields(target, a, b) {
    for (const key of new Set([
      ...Object.keys(a || {}),
      ...Object.keys(b || {}),
    ])) {
      if (a?.[key] === b?.[key]) continue;
      if (b?.[key] === undefined) delete target[key];
      else target[key] = b[key];
    }
  }
  mergeFields(out.defaults, before?.defaults, edited?.defaults);
  for (const group of ["all", "widgets"]) {
    for (const id of new Set([
      ...Object.keys(before?.[group] || {}),
      ...Object.keys(edited?.[group] || {}),
    ])) {
      const a = before?.[group]?.[id],
        b = edited?.[group]?.[id];
      if (JSON.stringify(a) === JSON.stringify(b)) continue;
      out[group][id] ||= {};
      mergeFields(out[group][id], a, b);
      if (!Object.keys(out[group][id]).length) delete out[group][id];
    }
  }
  return out;
}
