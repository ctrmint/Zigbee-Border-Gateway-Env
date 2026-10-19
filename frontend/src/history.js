export const historyKey = (w) =>
  [
    w.source.ieee,
    w.source.endpoint,
    w.source.cluster,
    w.source.attribute,
    w.time_range,
  ].join(":");
export function measurementFor(device, source) {
  return source.cluster === 65535
    ? device?.signal
    : device?.measurements.find(
        (m) =>
          m.endpoint === source.endpoint &&
          m.cluster === source.cluster &&
          m.attribute === source.attribute,
      );
}
export function geometry(data, fahrenheit = false, isState = false) {
  const number = (p) =>
    Number(fahrenheit && p.unit === "°C" ? (p.value * 9) / 5 + 32 : p.value);
  const valid = data.items.filter(
    (p) => p.value !== null && p.value !== undefined,
  );
  if (!valid.length) return null;
  const values = valid.map(number);
  let low = Math.min(...values),
    high = Math.max(...values);
  if (isState) {
    low = -0.1;
    high = 1.1;
  } else if (low === high) {
    low -= 1;
    high += 1;
  } else {
    const pad = (high - low) * 0.15;
    low -= pad;
    high += pad;
  }
  const x = (t) => 52 + ((t - data.from) / (data.to - data.from)) * 488,
    y = (v) => 180 - ((v - low) / (high - low)) * 156;
  let previous = null,
    path = "";
  for (const p of data.items) {
    if (p.value === null || p.value === undefined) {
      previous = null;
      continue;
    }
    const crosses =
      previous &&
      data.gaps.some(
        (g) => g.from <= p.received_at && g.to >= previous.received_at,
      );
    path +=
      (!previous || crosses ? "M" : isState ? "H" : "L") +
      x(p.received_at).toFixed(2) +
      (previous && !crosses && isState ? "V" : ",") +
      y(number(p)).toFixed(2);
    previous = p;
  }
  return { path, x, y, low, high, valid, number };
}
