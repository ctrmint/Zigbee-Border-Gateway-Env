# Dashboard appearance and editing

The Observatory dashboard uses React, Mantine and GridStack with the existing Python API and SQLite database. Its vivid monitoring-panel design takes inspiration from the [AlexNAS showcase](https://www.reddit.com/r/grafana/comments/g357u1/a_lot_of_people_have_been_showing_off_their/), [Aquamarine theme](https://docs.theme-park.dev/themes/grafana/) and Grafana stat/time-series panel patterns. Grafana is not installed, embedded or required. All assets stay local; no remote font service is used.

## Editing a dashboard

Choose **Edit layout** on All or a location. Drag by the grip, resize from the bottom-right corner, or select a tile and enter column, row, width and height. Coordinates start at zero; neighbouring tiles move down to make room. Choose Desktop, Tablet or Phone to edit that screen's layout independently. Normal viewing cannot drag or resize tiles. All tiles remain data-only; the editor action is in the page toolbar.

**Save layout** (All) or **Save location layout** persists the draft for the selected profile. **Discard changes** resets the draft; **Discard layout edits** closes a location editor. Navigating to a different tab/profile or disconnecting asks before discarding an open layout editor. Reloading/closing the page uses the browser's unsaved-changes prompt where supported. Changes are not saved by dragging or by navigating away. On conflict, explicitly reload/discard or reapply the draft against the latest configuration.

A location without saved widgets initially shows device readings. Add widgets (or use Add sensor widgets) before editing its widget grid. Widgets follow device location assignments. New automatic chart tiles use eight grid rows to leave room for the plot, summaries and controls; saved tile dimensions are retained. Existing layouts and the other profiles' preferences are retained.

## Typography and scale

In the layout editor select a tile/widget, then use **Typography & content scale**:

- **Content scale:** 75–150%, adjusting panel text and supporting labels. It does not change grid dimensions.
- **Metric font size:** 24–96 px before content scaling. A 60 px metric at 125% scale renders at 75 px. Chart headline values use 80% of this size to leave space for the plot; supporting plug diagnostics use 55% so key power/state readings remain prominent.
- **Metric typeface:** system sans, monospace, serif or rounded with system fallback. Actual installed system fonts may vary between devices. No font files or external requests are required.
- **Metric colour:** automatic theme/metric colour or a six-digit hex colour. The picker and input share the same setting. Incomplete hex input is not applied; enter all six digits. A warning identifies low contrast against the panel background. Status/freshness warnings remain independent of metric text colour.
- **Recorded trend sparkline:** show/hide an All tile's recent recorded trend. It does not request a new reading from a sensor.

Choose **Profile defaults** to set a base style for that profile, or **Selected tile override** for individual fields. Fields not overridden inherit profile defaults. **Use profile defaults** removes the selected tile's overrides; **Reset profile defaults** restores built-in typography. **Automatic colour** restores metric colours. A labelled synthetic typography sample and the draft panels provide a preview before saving.

Typography settings apply across Desktop/Tablet/Phone; grid geometry remains separate for each screen. Browser zoom continues to work. Large text in a small panel wraps or scrolls within the panel so full values remain available; increase grid width/height for comfortable large readings. Preview all target screens before saving.

Theme and style are profile preferences, not security settings. The default for layouts with no saved theme is dark; an explicitly saved light/dark choice is preserved. The light theme uses darker series colours for contrast. Setup → Preferences → Edit All dashboard layout also provides access to the profile theme selector.

## History and data quality

All optionally shows one recent-hour sparkline per device, prioritising temperature, then the first supported numeric non-battery metric. Its label identifies the metric. Each query is limited to 120 recorded samples, with at most two concurrent All queries and a minimum 60-second cache. Limit notices indicate a partial sample window. No history is invented when there are no valid samples. Navigating away or hiding the page cancels unfinished history queries; history caches retain only the active source/range set.

Location chart widgets share requests for the same source/range, use at most two concurrent queries, 500 samples/page and 20 pages/query. Requests are cached for at least 30 seconds and up to 60 seconds when the latest source is unchanged. Last/min/max summaries describe the returned samples within the selected period; a limit warning identifies incomplete results. Plots/fills break across invalid readings and recorded gaps. Pointer and keyboard inspection select actual samples. These visualisations do not change sensor reporting, relay settings or overload protection.

## Stored API fields

Dashboard v2 contract 2.10.0 adds optional `dashboard.grid_layout.presentation` version 1:

```json
{
  "version": 1,
  "defaults": {"size": 44, "font": "system", "scale": 100, "color": "auto"},
  "all": {"0123456789abcdef": {"size": 60, "trend": false}},
  "widgets": {"room-temperature": {"font": "mono", "color": "#38cdec"}}
}
```

`defaults` and per-ID styles contain sparse overrides. Allowed fields are `scale`, `size`, `font`, `color`, `trend` with the bounds/types above; there are at most 50 All and 100 widget entries. The server rejects malformed values atomically and requires the configuration ETag. GET projects missing defaults without rewriting storage. Older clients omitting `presentation` preserve saved styling; omitting all of `grid_layout` likewise preserves it. An explicit empty presentation document resets overrides. Reapplying a draft retains unrelated styles added by another editor. The configuration body remains subject to the existing 64 KiB bound.

Related delivery tickets: #35, #37, #38, #39 and #40. Software/browser checks do not substitute for the user's visual acceptance or physical iPad Safari checks.

## Design examples

These screenshots use synthetic devices and generated history, not household data. They demonstrate the panel design; they are not evidence of physical iPad acceptance.

- [All overview](images/dashboard-observatory-all.png)
- [Location and history panels](images/dashboard-observatory-location.png)
- [Tablet portrait layout](images/dashboard-observatory-tablet.png)

The user accepted this build on 19 October 2026. It is deployed on the normal dashboard port **8080** with the existing token; the temporary review on 8081 is retired. Physical iPad checks and extended observation remain separately recorded in the issue checklists.
