import { test } from "node:test";
import assert from "node:assert/strict";
import {
  emptyPresentation,
  metricStyle,
  mergePresentation,
  contrast,
} from "./presentation.js";
import { mergeAllLayout, emptyLayout } from "./layout.js";
import { areaPath, geometry } from "./history.js";
test("profile defaults inherit, sparse overrides win, other tiles and screens stay independent", () => {
  const layout = { presentation: emptyPresentation() };
  layout.presentation.defaults = { size: 52, font: "mono", color: "#38cdec" };
  layout.presentation.all.a = { size: 72, scale: 125 };
  assert.equal(metricStyle(layout, "all", "a").size, 72);
  assert.equal(metricStyle(layout, "all", "b").size, 52);
  assert.equal(metricStyle(layout, "widgets", "a").font, "mono");
  delete layout.presentation.all.a;
  assert.equal(metricStyle(layout, "all", "a").size, 52);
});
test("explicit reapply changes edited presentation fields and retains concurrent unrelated styles", () => {
  const before = emptyPresentation(),
    edited = structuredClone(before),
    current = structuredClone(before);
  edited.all.a = { size: 60 };
  current.widgets.b = { font: "mono" };
  current.defaults = { color: "#ffffff" };
  const merged = mergePresentation(current, before, edited);
  assert.equal(merged.all.a.size, 60);
  assert.equal(merged.widgets.b.font, "mono");
  assert.equal(merged.defaults.color, "#ffffff");
  const latest = emptyLayout();
  latest.presentation = current;
  const draft = emptyLayout();
  draft.presentation = edited;
  assert.deepEqual(
    mergeAllLayout(latest, draft, { presentation: before }).presentation,
    merged,
  );
});
test("contrast calculations distinguish invisible and readable colours", () => {
  assert.equal(contrast("#ffffff", "#ffffff"), 1);
  assert.equal(contrast("#000000", "#ffffff"), 21);
  assert.ok(contrast("#38cdec", "#152538") > 4.5);
});
test("area fills preserve segment gaps and invalid numeric samples break paths", () => {
  const data = {
    from: 0,
    to: 10,
    gaps: [],
    items: [
      { received_at: 1, value: 0 },
      { received_at: 2, value: 2 },
      { received_at: 3, value: 4, quality: "invalid" },
      { received_at: 5, value: 5 },
      { received_at: 6, value: 6 },
    ],
  };
  const p = geometry(data);
  assert.equal(p.valid.length, 4);
  assert.equal(p.path.split("M").length - 1, 2);
  assert.equal(areaPath(p.path).split("Z").length - 1, 2);
});

test("reapply retains concurrent changes to a different field on the same tile", () => {
  const before = emptyPresentation();
  before.all.a = { size: 44 };
  const edited = structuredClone(before);
  edited.all.a.size = 64;
  const current = structuredClone(before);
  current.all.a.font = "mono";
  assert.deepEqual(mergePresentation(current, before, edited).all.a, {
    size: 64,
    font: "mono",
  });
});

test("font-only All reapply retains concurrent theme and screen geometry", () => {
  const before = emptyLayout(),
    edited = structuredClone(before),
    current = structuredClone(before);
  edited.presentation = emptyPresentation();
  edited.presentation.all.a = { size: 64 };
  current.theme = "light";
  current.all.mobile = [{ id: "a", x: 0, y: 0, w: 1, h: 5 }];
  const result = mergeAllLayout(current, edited, before);
  assert.equal(result.theme, "light");
  assert.deepEqual(result.all.mobile, current.all.mobile);
});
