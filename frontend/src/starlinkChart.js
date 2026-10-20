export const CHART_HEIGHT = 360;
export const CHART_MARGIN = { top: 20, right: 16, bottom: 48, left: 66 };
export const MAX_SAMPLE_GAP_SECONDS = 120;

function niceStep(raw) {
  const power = 10 ** Math.floor(Math.log10(raw));
  const fraction = raw / power;
  return (fraction <= 1 ? 1 : fraction <= 2 ? 2 : fraction <= 2.5 ? 2.5 : fraction <= 5 ? 5 : 10) * power;
}

export function makeYAxis(values, targetTicks = 5) {
  const finite = values.filter(Number.isFinite);
  const maximum = Math.max(0, ...finite);
  const step = niceStep((maximum || 1) / Math.max(1, targetTicks - 1));
  const upper = Math.max(step, Math.ceil(maximum / step) * step);
  const precision = step >= 1 ? 0 : Math.min(6, Math.max(1, -Math.floor(Math.log10(step))));
  return { min: 0, max: upper, ticks: Array.from({ length: Math.round(upper / step) + 1 }, (_, i) => i * step), format: (value) => Number(value.toFixed(precision)).toString() };
}

export function timeTicks(start, end, target = 5) {
  const span = Math.max(1, end - start);
  const intervals = [60, 300, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400, 172800, 604800, 1209600, 2592000];
  const step = intervals.find((value) => span / value <= target) || intervals.at(-1);
  const ticks = [];
  for (let value = Math.ceil(start / step) * step; value <= end; value += step) ticks.push(value);
  if (!ticks.length || ticks[0] > start) ticks.unshift(start);
  if (ticks.at(-1) < end && ticks.length < target + 1) ticks.push(end);
  return ticks;
}

export function formatTime(timestamp, span, compact = false) {
  const date = new Date(timestamp * 1000);
  if (compact && span >= 86400 && span < 86400 * 180)
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  return span < 86400
    ? date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : span < 86400 * 180
      ? date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })
      : date.toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" });
}

export function buildChartModel(history, fields, width) {
  const plot = { x: CHART_MARGIN.left, y: CHART_MARGIN.top, width: Math.max(100, width - CHART_MARGIN.left - CHART_MARGIN.right), height: CHART_HEIGHT - CHART_MARGIN.top - CHART_MARGIN.bottom };
  const samples = history.map((sample, index) => ({ sample, index, time: Number(sample.received_at) }))
    .filter(({ sample, time }) => sample.status === "available" && Number.isFinite(time) && fields.some((field) => Number.isFinite(sample[field.key] * field.factor)));
  if (samples.length < 2) return { samples, plot, lines: [], yAxis: makeYAxis([]), ticks: [], start: 0, end: 0 };
  const start = Math.min(...samples.map((point) => point.time));
  const end = Math.max(...samples.map((point) => point.time));
  const span = Math.max(1, end - start);
  const transform = (time, value) => ({ x: plot.x + ((time - start) / span) * plot.width, y: plot.y + plot.height - (value / yAxis.max) * plot.height });
  const values = fields.flatMap((field) => samples.map(({ sample }) => sample[field.key] * field.factor).filter(Number.isFinite));
  const yAxis = makeYAxis(values);
  const lines = fields.map((field) => {
    const segments = [];
    let segment = [];
    let previousTime = null;
    history.forEach((sample, index) => {
      const time = Number(sample.received_at);
      const value = sample.status === "available" ? sample[field.key] * field.factor : null;
      if (!Number.isFinite(time) || !Number.isFinite(value) || (previousTime !== null && time - previousTime > MAX_SAMPLE_GAP_SECONDS)) {
        if (segment.length > 1) segments.push(segment);
        segment = [];
      }
      if (Number.isFinite(time) && Number.isFinite(value)) {
        segment.push({ ...transform(time, value), value, time, index, field });
        previousTime = time;
      } else previousTime = null;
    });
    if (segment.length > 1) segments.push(segment);
    return { field, segments };
  });
  return { samples, plot, lines, yAxis, ticks: timeTicks(start, end, width < 420 ? 3 : 5), start, end };
}

export function nearestChartPoint(model, target, maxDistance = 24) {
  let nearest = null;
  for (const line of model.lines) for (const segment of line.segments) for (const point of segment) {
    const distance = Math.hypot(target.x - point.x, target.y - point.y);
    if (!nearest || distance < nearest.distance) nearest = { ...point, distance };
  }
  return nearest && nearest.distance <= maxDistance ? nearest : null;
}
