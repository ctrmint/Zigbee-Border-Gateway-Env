# All dashboard layout (#25)

Open **Configuration & Setup → All dashboard layout**. Settings belong to the selected profile shown in the heading. Choose **Tiles across**, adjust **Minimum tile width (pixels)**, and use the up/down buttons to arrange the sensor order. Press **Save All layout** to apply all changes, or **Discard layout edits** to return to the saved settings. Profile switches discard unsaved edits, and conflicting saves use the existing reload/reapply workflow.

- **Auto** fits as many tiles as the available width allows and collapses unused columns, preserving the original overview behavior. Auto can use more than six columns on a sufficiently wide screen.
- **1–6 columns** requests that number of equal-width columns. Empty slots remain when there are fewer sensors than requested columns. A single column makes each tile use the available row width.
- **Minimum tile width** accepts 200–640 pixels in steps of 20; the default is 240. It applies in both modes. Wider values give fewer, wider tiles; narrower values fit more tiles.
- The width needed for readable tiles takes precedence over a requested count. Narrow screens/Split View and enlarged root text can reduce the effective count, down to one full-width tile. All shows the effective column count and says when fewer than requested fit. These are preferred minimum widths, not a reason to overflow a narrow screen.

Rotation and window resizing reflow the grid immediately without a reload. Tiles share the available width equally; individual tiles do not have custom spans or unequal column sizes. All remains a read-only display: its grid contains no buttons, links, editing actions or drag handles. Signal strength/age, measurements, units and all existing stale/missing/low-battery/offline indications remain visible. Changing or viewing layout does not request Zigbee reads or chart history.

## Ordering and profiles

Saved sensor addresses determine reading order from left to right, then top to bottom. New unranked sensors follow the saved order, sorted by stable IEEE address. Renaming or changing readings/locations does not reorder tiles. Departed/unavailable sensors are hidden from All as before; their saved place is retained for when they return. Saved absent addresses appear in Setup as **Not currently shown**. An empty saved order uses the original IEEE ordering. Saving the editor records the listed order, including currently visible sensors.

Each profile has its own `dashboard.all_layout`; layouts remain across reloads and Pi restarts. Other profiles, location widgets, shared names/locations, reporting policies and measurement history are unaffected. Profiles are convenience settings without login or roles.

## API and compatibility

Authenticated v2 configuration GET/PUT exposes this optional additive dashboard property (introduced in contract 2.6.0; see the generated contract for the current version):

```json
"all_layout": {"columns": 0, "min_tile_width": 240, "order": []}
```

`columns` is an integer 0–6 (0 means Auto); `min_tile_width` is an integer 200–640 and a multiple of 20. `order` contains at most 50 unique lowercase 16-digit IEEE addresses. Well-formed absent addresses are retained without creating devices. Unknown fields and invalid types/counts/widths/order are rejected atomically. Existing profile selection and If-Match revision checks apply to the entire configuration.

Old stored JSON is projected with default Auto/240/empty-order settings without rewriting data or revisions. An older client omitting `all_layout` during a PUT preserves the currently saved value. New profiles receive the same defaults. No firmware or database schema change is required.

## Deployment and rollback

Back up the configured SQLite database and source, then restart only the Pi dashboard service and refresh the browser. Firmware, Zigbee network and existing layouts need no changes. Before restoring older software, retain newer history and back up current profile settings: older configuration validators cannot save JSON containing this new field. Restore matching source/configuration safely with the service stopped; avoid replacing newly recorded measurements with an older snapshot merely to change presentation settings.

Automated Chromium and WebKit tablet checks are recorded in [validation](VALIDATION.md). The user confirmed physical iPad acceptance and [#25](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/25) is closed. Detailed device/version and individual gesture/orientation results were not supplied. Layout applies to supported metering-plug tiles as well as sensors; later plug-specific physical Safari acceptance remains in #27.
