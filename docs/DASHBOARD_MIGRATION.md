# React / Mantine / GridStack dashboard (#34)

## Current interface

The React dashboard is the primary interface at `/` on the existing Python service (normally port 8080). The old HTML/controller/CSS dashboard has been removed. `/next` and `/next/` redirect to `/` for older links; they do not host a second interface. The temporary port-8081 review service is stopped when this build is deployed.

The user confirmed that the framework and location navigation work, and requested replacing the old dashboard. **The appearance was explicitly reported as too similar to the original.** This is functional migration acceptance, not visual acceptance. A distinctly new design is tracked in [#35](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/35). Full physical iPad Safari acceptance remains separate from automated WebKit checks.

All remains a compact data-only overview with temperature/humidity, battery, plug telemetry, metric age/quality and coordinator-reception RSSI. Location tabs show saved numeric/chart widgets in position order, or assigned-device readings when the profile has no widgets. Setup stays right, locations left and profile selection top right. All is the initial view after connecting.

## Setup and device controls

Configuration & Setup now contains Mantine sections for Gateway, Devices, Locations, Profiles, Preferences and Diagnostics. It retains pairing/close, discovery/reads, shared names/freshness/assignments, location/profile management, title/temperature preferences, reporting setup/readback/cancellation, SNZB-02UL scalar E-Ink settings and S60ZBTPG controls. In a location, identified plugs retain explicit On/Off requests and job status. Generic actuator controls remain gated by endpoint capabilities; a sensor's protocol On/Off cluster is not an appliance control.

Viewing pages performs authenticated GETs only. Pairing, reads, discovery, reporting and device writes require explicit actions. Jobs distinguish accepted, queued, verified, acknowledged/unverified, failed, uncertain and cancelled states; HTTP acceptance does not confirm a relay change. Writes are not retried automatically. Plug protection limits remain 13 A / 3250 W; complete thresholds and protection enable are separate actions. Current/raw settings and capability limitations remain in diagnostics. Manufacturer/OTA/timing restrictions from the existing APIs are unchanged.

Profiles have no login or security roles. Device state, names, locations and history remain shared; widget/layout/theme preferences are separate. The session cookie remembers profile selection, while bearer tokens remain only in page memory. Disconnect/profile changes abort pending requests and discard unsaved editors. Setup forms preserve local drafts through polling and use ETag conflict handling; users explicitly reload/discard or reapply edits to the latest configuration.

See [appearance and editing](DASHBOARD_APPEARANCE.md) for the monitoring theme, metric typography, scaling and saved layouts.

## Widgets and layout

Location pages support adding/editing/removing widgets, suggested numeric/chart widgets, saved chart ranges and order controls. Where a screen has a custom geometry, use **Edit layout** rather than up/down order buttons; this avoids discarding custom sizes/other screen layouts. Widgets continue following their device's location assignment.

Open Setup → Preferences → **Edit All dashboard layout** for the read-only overview's separate editor. Location widgets have their own **Edit layout** editor. Both use GridStack drag/resize plus accessible numbered column/row/width/height controls. Save, discard and reset are explicit; dragging never saves on its own. Desktop (viewport at least 1100 px), tablet (700–1099 px) and phone layouts are saved independently with 12, six and one columns respectively. Grid rows are 72 px. Browser resizing never writes projected coordinates back to storage. Narrow/short cards can scroll internally rather than silently omit readings.

Dashboard-v2 contract **2.10.0** adds `dashboard.grid_layout`:

```json
{
  "version": 1,
  "theme": "light",
  "all": {"desktop": [], "tablet": [], "mobile": []},
  "locations": {
    "location-id": {
      "desktop": [{"id": "widget-id", "x": 0, "y": 0, "w": 6, "h": 6}],
      "tablet": [],
      "mobile": []
    }
  }
}
```

All tile IDs are IEEE addresses; location tile IDs are widget IDs. Coordinates must be integers, x/width must fit the screen's columns, y is 0–1000 and height 3–20. Each All screen allows 50 unique, non-overlapping rectangles; each location screen allows 100, across at most 50 location layouts. Server validation rejects malformed/overlapping geometry atomically.

GET projects defaults without rewriting existing records/revisions. Empty All geometry derives deterministic placement from the previous columns/minimum-width/order preferences. Empty location geometry derives from existing widget positions. No names, assignments, charts, profiles or history are discarded to migrate. A client omitting `grid_layout` on PUT preserves it; an early preview client supplying a grid without `locations` preserves existing location geometry. Absent tile records are retained; explicit edits can move absent records below the edited surface to keep returning tiles collision-free. Reset explicitly returns that screen to derived placement.

## Browser ownership and requests

GridStack owns wrapper elements/geometry; React owns their contents through portals. There is one grid instance per mounted screen/editor, cleaned up with its handlers on unmount. Device strings are rendered as text, not injected HTML. Saved data contains only semantic IDs/coordinates, never generated HTML or callbacks.

A sequential abortable polling cycle obtains state/configuration/device views/profiles every four seconds (15 seconds when hidden). Setup additionally polls stored reporting/display jobs and caches the profile reference; those GETs do not contact the radio. Identical chart source/range pairs share history requests, with at most two concurrent paginated queries, 500 samples/page and at most 20 pages/query. History is cached for at least 30 seconds and up to 60 seconds while the latest source is unchanged. Leaving a location/profile or disconnecting aborts its pending history work. All optionally queries bounded recorded-history sparklines; see [appearance and editing](DASHBOARD_APPEARANCE.md) for limits and styling.

Charts preserve real zero, null/invalid readings, raw units and source times. Lines break across known gaps/nulls; shading marks recorded interruptions. Source/receipt estimates and static capability metadata retain their existing meanings. Partial response limits are labelled. Pointer/keyboard inspection selects actual samples; no data is invented to fill a gap.

## Build and dependencies

Use Node.js 22.12+ (development used 22.23.3) and npm **at build time only**:

```bash
cd frontend
npm ci
npm test
npm run build
```

The dependency graph is pinned in `package-lock.json`: React/React DOM 19.3.1, Mantine Core/Hooks 9.7.3, GridStack 14.0.0, Lucide React 1.59.0, Vite 8.3.4 and the React plugin 6.1.2. Prettier formats source. Production assets and licence notices are committed in `sbc/static/dashboard/`; Python serves them without Node, a CDN, external fonts or cloud dependencies. Setup is loaded as a separate chunk. No local credentials are included in the bundle.

The serving policy restricts scripts to same-origin and permits dynamic styles needed by Mantine/GridStack; asset paths are bounded to the bundle directory. API authentication remains unchanged. Browser baselines from [Mantine](https://mantine.dev/browser-support/) are dependency documentation, not certification of this installation's iPad. Consult the [Mantine Vite guide](https://mantine.dev/guides/vite/) and [GridStack API](https://gridstackjs.com/doc/html/classes/GridStack.html).

## Validation, deployment and rollback

Run API tests with `python3 -m unittest discover -s tests -v`, contracts with `python3 -m sbc.contracts --check`, and frontend tests/build above. The replacement Playwright suite is `tests/browser_dashboard.py`, using fixtures in `browser_support.py`; obsolete tests tied to the removed DOM were replaced with framework/workflow tests. Synthetic device-action cases are distinct from live GET-only checks. WebKit iPad emulation is distinct from physical touch acceptance.

Before deploying, take a consistent SQLite backup and retain the preceding source/static assets. Deploy Python and the committed bundle together, then restart only the Pi dashboard service. Firmware, Wi-Fi, Zigbee network and pairing are unchanged. Existing source/history/configuration remain in the live database; a private review snapshot must never replace production history merely to adopt a layout. Remove the temporary preview service after the primary interface is verified. The `v0.0.1` release tag remains unchanged.

Rollback uses the saved previous source and only restores matching configuration deliberately. Older validators cannot save a supplied `grid_layout` field. Remove/project only that presentation field if necessary for an older client, with the dashboard stopped and a current backup retained; do not restore an old measurement database just to change the UI.

`scripts/preview_dashboard.py` remains a development helper for isolated review with a private SQLite snapshot. It forwards authenticated read-only state/device/history/job/reference GETs to the installed service and saves preview configuration only in its copy; device/profile actions are disabled. It is not a second installed production dashboard.
