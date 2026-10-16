# All sensors overview

After connecting with your dashboard token, select **All** at the left of the tab bar. It shows one automatically generated tile per registered sensor, including sensors without a location. Location tabs remain available and Configuration & Setup stays on the right. Login still opens the first saved location, or Setup when no locations exist.

Tiles contain data only: the sensor name, location, supported readings, units and the age/status of each reading. There are no tile controls, links, editing actions or radio-read buttons. Manage names, locations, units and freshness in Setup; existing location widgets remain independently configurable.

Temperature-only sensors have no humidity placeholder. Battery percentage or voltage appears only when exposed by the device API; battery reporting/normalization is separate sensor work in #14. Multiple endpoints share a tile, with endpoint labels when needed. By default sensors are ordered by stable device address. Each profile can now set columns, preferred tile width and sensor order in Setup; see [All layout settings](ALL_LAYOUT.md). Renaming, assigning a location or receiving data does not reorder saved placement. Actuator-only devices and departed sensors are excluded. A device still awaiting discovery cannot be identified as a sensor until capabilities or a known sensor profile are available.

**Stale**, **Invalid reading**, **No reading** and **Low battery** are explicit text labels. Each measurement retains its own timestamp/freshness; battery freshness is independent of temperature. A gateway outage is shown separately above the tiles, and cached readings keep their ages. Opening this page does not trigger radio measurements or download chart history.

The overview uses the full available width, a compact header and a responsive tile grid. Portrait, landscape and narrow tablet/Split View layouts reflow without reload. Scroll vertically for additional sensors; there is no pagination. Values update without replacing the whole grid or forcing the scroll position. Use Safari's normal text/page enlargement as needed. Navigation tabs support touch and arrow/Home/End keyboard navigation.

## Validation

Automated Chromium coverage includes mixed capabilities, unassigned sensors, multiple endpoints, unknown/missing/invalid values, battery warnings, offline/API failure and recovery, logout, data-only markup, no extra command/history requests, stable tiles/scroll, long names, 31 sensors and viewport widths 390/507/768/1024/1180 pixels. Layout is also checked at 200% page zoom. The full existing dashboard browser suite is retained.

Actual iPad Safari verification remains pending. Desktop automation and WebKit checks cannot establish behavior on a physical iPad. Record iPad model, iPadOS/Safari version, portrait/landscape, Split View, touch scrolling/tab selection and text enlargement results in issue #18 when a device is available.

## Deployment and rollback

The original overview modified static dashboard assets. Its subsequent [per-profile layout settings](ALL_LAYOUT.md) also extend the Pi configuration API; they require a Pi service restart, with no firmware or database schema change. Refresh an already open dashboard page and reconnect with the existing token. No service or coordinator restart is required for the static assets. Local private backups contain the previous assets and a consistent snapshot of the configured hardware database; restore the assets to roll back the overview without reverting live history.

The nine All-tab/navigation cases also pass with Playwright WebKit and the `iPad (gen 7)` touch/device profile. To run these suites in a configured Playwright environment:

```sh
DASHBOARD_TEST_BROWSER=webkit DASHBOARD_TEST_DEVICE='iPad (gen 7)' \
  PYTHONPATH=.:tests python3 -m unittest browser_all browser_navigation -v
```

See the [validation record](VALIDATION.md) for counts, environment details and the remaining physical-device check.
