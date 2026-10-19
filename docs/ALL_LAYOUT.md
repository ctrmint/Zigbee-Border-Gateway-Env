# All dashboard layout

The primary dashboard now uses the [GridStack layout editor](DASHBOARD_MIGRATION.md).
Use **Edit layout** on All (also available through **Configuration & Setup → Preferences → Edit All dashboard layout**) to arrange
and size tiles independently for desktop, tablet and phone. Save/discard/reset
are explicit, with drag/resize and numbered keyboard-accessible controls. The All
page itself remains data-only. Theme/layout choices belong to the selected profile.

Previous columns, minimum widths and order remain stored as `dashboard.all_layout`
and determine initial placement until explicit `grid_layout` geometry is saved.
No existing profiles, locations, widgets, readings or history are erased. The former
equal-width column/order editor is replaced by individual tile geometry. For custom
location widgets use **Edit layout** in the location tab.

See the migration guide for the versioned contract, conflict handling, bounds,
legacy request preservation, deployment/rollback and physical iPad acceptance limits.

See [appearance and editing](DASHBOARD_APPEARANCE.md) for profile defaults, per-tile fonts, colours, content scale and recorded-history sparklines.
