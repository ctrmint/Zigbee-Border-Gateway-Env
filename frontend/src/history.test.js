import { test } from "node:test";
import assert from "node:assert/strict";
import { geometry, historyKey } from "./history.js";
test("zero values remain valid and paths break on gaps and invalid readings", () => {
  const data = {
    from: 0,
    to: 10,
    gaps: [{ from: 3, to: 4 }],
    items: [
      { received_at: 1, value: 0, unit: "W" },
      { received_at: 2, value: 1, unit: "W" },
      { received_at: 5, value: 2, unit: "W" },
      { received_at: 6, value: null, unit: "W" },
      { received_at: 7, value: 3, unit: "W" },
    ],
  };
  const p = geometry(data);
  assert.equal(p.valid.length, 4);
  assert.equal(p.path.split("M").length - 1, 3);
  assert.ok(p.path.includes("L"));
  assert.equal(geometry({ ...data, items: [] }), null);
});
test("fahrenheit conversion and state step paths preserve source values", () => {
  const data = {
    from: 0,
    to: 10,
    gaps: [],
    items: [
      { received_at: 1, value: 0, unit: "°C" },
      { received_at: 2, value: 10, unit: "°C" },
    ],
  };
  assert.equal(geometry(data, true).number(data.items[0]), 32);
  assert.equal(data.items[0].value, 0);
  assert.ok(
    geometry(
      {
        ...data,
        items: data.items.map((p) => ({
          ...p,
          value: !!p.value,
          unit: "on/off",
        })),
      },
      false,
      true,
    ).path.includes("H"),
  );
  const w = {
    source: { ieee: "a", endpoint: 1, cluster: 1026, attribute: 0 },
    time_range: 3600,
  };
  assert.equal(historyKey(w), historyKey({ ...w, title: "Other title" }));
});
