import test from "node:test";
import assert from "node:assert/strict";
import { buildChartModel, makeYAxis, nearestChartPoint, timeTicks } from "./starlinkChart.js";

const field = { key: "down", label: "Download", color: "line", factor: 1e-6, unit: "Mbps", format: (value) => `${value} Mbps` };
const point = (received_at, down, status = "available") => ({ received_at, down, status });

test("Y axis starts at zero and chooses readable labeled divisions", () => {
  const axis = makeYAxis([0.7, 3.2]);
  assert.equal(axis.min, 0);
  assert.ok(axis.max >= 3.2);
  assert.ok(axis.ticks.length >= 3);
  assert.equal(axis.ticks[0], 0);
});

test("time ticks cover a range and chart x positions follow elapsed time", () => {
  const model = buildChartModel([point(1000, 1_000_000), point(1050, 2_000_000), point(1150, 3_000_000)], [field], 500);
  const plotted = model.lines[0].segments.flat();
  assert.equal(plotted[0].x, model.plot.x);
  assert.ok(Math.abs((plotted[1].x - plotted[0].x) - model.plot.width / 3) < 0.001);
  assert.equal(plotted[2].x, model.plot.x + model.plot.width);
  assert.ok(timeTicks(1000, 1240).length >= 2);
});

test("missing samples and long polling gaps break lines without interpolation", () => {
  const history = [point(1000, 1_000_000), point(1060, 2_000_000), point(1120, null, "unavailable"), point(1180, 3_000_000), point(1400, 4_000_000), point(1460, 5_000_000)];
  const model = buildChartModel(history, [field], 500);
  assert.equal(model.lines[0].segments.length, 2);
  assert.deepEqual(model.lines[0].segments.map((segment) => segment.length), [2, 2]);
});

test("nearest point interaction returns the source time and transformed value", () => {
  const model = buildChartModel([point(1000, 1_000_000), point(1060, 2_000_000)], [field], 500);
  const expected = model.lines[0].segments[0][1];
  assert.equal(nearestChartPoint(model, { x: expected.x, y: expected.y }).time, 1060);
  assert.equal(expected.value, 2);
  assert.equal(nearestChartPoint(model, { x: 5000, y: 5000 }), null);
});
