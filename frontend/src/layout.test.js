import { test } from "node:test";
import assert from "node:assert/strict";
import {
  effectiveLayout,
  emptyLayout,
  overlaps,
  mergePresent,
  editItem,
  serializeGridItems,
  quality,
  display,
} from "./layout.js";
const devices = [
  { ieee: "a", measurements: [] },
  { ieee: "b", measurements: [] },
  { ieee: "c", measurements: [], plug: {} },
];
const legacy = { columns: 2, min_tile_width: 240, order: ["b", "a"] };
test("GridStack serialization always supplies the required layout fields", () => {
  const items = serializeGridItems([
    {
      gridstackNode: { x: 2, y: 3, w: 4, h: 6 },
      dataset: { sensorId: "power-now" },
      getAttribute: () => null,
    },
    {
      gridstackNode: { id: "temperature", x: 0, y: 0, w: 6, h: 4 },
      dataset: {},
      getAttribute: () => null,
    },
  ]);
  assert.deepEqual(items, [
    { id: "power-now", x: 2, y: 3, w: 4, h: 6 },
    { id: "temperature", x: 0, y: 0, w: 6, h: 4 },
  ]);
  assert.deepEqual(Object.keys(items[0]).sort(), ["h", "id", "w", "x", "y"]);
});
test("legacy order migrates deterministically without mutating preferences", () => {
  const settings = emptyLayout(),
    before = structuredClone(settings),
    nodes = effectiveLayout(devices, settings, legacy, "desktop");
  assert.deepEqual(
    nodes.map((n) => n.id),
    ["b", "a", "c"],
  );
  assert.equal(nodes[0].w, 6);
  assert.deepEqual(settings, before);
  for (let i = 0; i < nodes.length; i++)
    for (let j = 0; j < i; j++) assert.ok(!overlaps(nodes[i], nodes[j]));
});
test("breakpoint edits retain absent devices and do not change other layouts", () => {
  const settings = emptyLayout();
  settings.all.desktop = [{ id: "z", x: 0, y: 0, w: 4, h: 4 }];
  const present = effectiveLayout(devices, settings, legacy, "desktop");
  const merged = mergePresent(settings.all.desktop, present);
  assert.equal(merged.at(-1).id, "z");
  assert.ok(merged.at(-1).y >= Math.max(...present.map((n) => n.y + n.h)));
  assert.deepEqual(settings.all.tablet, []);
});
test("keyboard resizing pushes neighbours and stays within bounds", () => {
  const nodes = effectiveLayout(devices, emptyLayout(), legacy, "tablet");
  const result = editItem(nodes, "b", { x: 5, w: 5, h: 5 }, 6);
  assert.equal(result[0].x, 1);
  assert.equal(result[0].w, 5);
  for (let i = 0; i < result.length; i++)
    for (let j = 0; j < i; j++) assert.ok(!overlaps(result[i], result[j]));
});
test("stale zero, missing and invalid remain distinct; raw telemetry is not replaced", () => {
  assert.equal(
    quality(
      { value: 0, quality: "valid", received_at: 1, freshness_seconds: 60 },
      100,
    ),
    "stale",
  );
  assert.equal(display({ value: 0, unit: "W" }).value, "0");
  assert.equal(display({ value: null, unit: "W" }).value, "—");
  assert.equal(quality({ value: null, quality: "missing" }), "missing");
  assert.equal(quality({ value: null, quality: "invalid" }), "invalid");
  assert.equal(display({ value: 0, unit: "°C" }, "fahrenheit").value, "32");
});

test("location widgets migrate order and preserve geometry independently of All", async () => {
  const { widgetLayout } = await import("./layout.js");
  const widgets = [
    { id: "a", type: "chart", position: 1 },
    { id: "b", type: "numeric", position: 0 },
  ];
  const auto = widgetLayout(widgets, {}, "desktop");
  assert.equal(auto[0].id, "b");
  assert.equal(auto[0].w, 6);
  const saved = {
    desktop: [{ id: "a", x: 0, y: 5, w: 12, h: 6 }],
    tablet: [],
    mobile: [],
  };
  const nodes = widgetLayout(widgets, saved, "desktop");
  assert.equal(nodes.find((n) => n.id === "a").w, 12);
  assert.ok(!overlaps(nodes[0], nodes[1]));
  assert.equal(widgetLayout(widgets, saved, "mobile")[0].w, 1);
});

test("All layout reapply preserves the latest location geometry", async () => {
  const { mergeAllLayout } = await import("./layout.js");
  const current = emptyLayout();
  current.locations.room = {
    desktop: [{ id: "widget", x: 0, y: 0, w: 4, h: 4 }],
    tablet: [],
    mobile: [],
  };
  const edited = emptyLayout();
  edited.theme = "dark";
  const merged = mergeAllLayout(current, edited);
  assert.deepEqual(merged.locations, current.locations);
  assert.equal(merged.theme, "dark");
});
