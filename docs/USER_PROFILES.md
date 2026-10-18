# User profiles and browser sessions (#20)

Choose a profile from **Profile** at the top right of the dashboard after connecting with the existing dashboard token. Profiles require no individual login or password. Anyone using the dashboard can choose or manage any profile; Admin is the default name, not a privileged role.

## Presentation and shared data

Each profile owns its dashboard title, Celsius/Fahrenheit preference and widget layout (including widget titles, order, types and time ranges). Admin retains the installation's existing configuration. New profiles start with title Home, Celsius and an empty saved layout; the automatic All overview still shows shared sensors and supported metering plugs. Initial connection continues to open the first location, or Setup when there are no locations. Switching profiles keeps the current tab where it remains available.

Sensors, physical locations/assignments, device names, freshness thresholds, history, gateway settings, commissioning and controls are shared. Editing these in Setup affects everyone. A layout/preference save only updates the selected profile. Shared metadata changes invalidate affected configuration revisions across profiles, while one profile's layout-only save does not invalidate another's. There is no access-control boundary between profiles.

## Setup management

Configuration & Setup → User profiles adds, renames and deletes profiles. Names must contain 1–80 visible characters; case/compatibility-equivalent duplicates are rejected. There are at most 20 profiles including Admin. IDs stay the same when a profile is renamed. Admin remains available and cannot be renamed or deleted. Deleting another profile removes its saved presentation, while sensor data and other profiles remain intact.

Profile lists and layouts are stored on the Pi and survive service/Pi restarts. Selection belongs to each browser cookie context. Different browser sessions can use different profiles simultaneously; tabs sharing a cookie context share the selection. A change in another tab is detected on focus, refresh or before a mutation.

Switching profiles **discards unsaved edits**, closes an open widget editor, cancels pending client requests and clears presentation/chart caches. A request already transmitted can complete against its original profile. Its captured profile ID and scoped revision prevent it from saving into the newly selected profile, and old responses cannot populate the new session view. Deleted-profile writes return a conflict instead of saving into Admin.

## Session cookie

The first-party `dashboard_profile` cookie contains only a stable profile ID. It has `Path=/; SameSite=Lax` and **no Expires or Max-Age**, Secure or HttpOnly requirement; it works with the current HTTP dashboard and is readable by its JavaScript. It never contains dashboard/gateway credentials and has no authorisation effect.

Reload/navigation restores the cookie's selection. A new cookie context defaults to Admin. Browser session restore may preserve session cookies, so closing a window is not guaranteed to clear the selection. Missing, malformed, unknown and deleted selections fall back to Admin. If cookie writes are unavailable, selection still works for the current page through explicit request context, with a visible notice; a later page load uses the available cookie or Admin.

## API

Existing dashboard bearer-token access remains required. Profile choice adds no credentials.

- `GET /api/v2/profiles`: shared profile list and selected context.
- `POST /api/v2/profiles` with `{"name":"Mark"}`: create a profile.
- `PUT /api/v2/profiles/{profile_id}` with a name: rename.
- `DELETE /api/v2/profiles/{profile_id}`: delete non-default profile presentation.
- `GET/PUT /api/v2/configuration`: presentation for the selected profile, with shared metadata.

Requests resolve `X-Dashboard-Profile` first, then the `dashboard_profile` cookie, then Admin. The explicit header freezes asynchronous request context even if the browser cookie changes before delivery. Configuration responses identify the actual context in `X-Dashboard-Profile` and include an ETag. Use the exact ETag for PUT. Admin's existing `configuration-N` ETags remain compatible; other profiles include their stable ID. No global active-user variable is used. Other sensor/history endpoints remain shared.

See the generated [v2 contract](api/dashboard-v2.openapi.json) for payloads/errors and the `user_profiles` capability. Invalid/deleted selections fall back on reads; writes with an unavailable context return 409 so fallback cannot overwrite Admin.

## Validation, deployment and rollback

Automated coverage exercises migration/restart, concurrent profiles and revisions, shared metadata, management validation/limits, cookie/header resolution, cookie restoration/blocking, multiple browser sessions/tabs, rename/delete, late saves and responsive tablet layout. WebKit with an emulated iPad touch profile is recorded separately from physical iPad acceptance. The user confirmed that acceptance and [#20](https://github.com/ctrmint/Zigbee-Border-Gateway-Env/issues/20) is closed. Device/version and detailed interaction results were not supplied; this does not imply physical acceptance of later plug-specific controls.

Before updating, stop the dashboard service and back up its **configured** database path from `.env`, plus current source. Migration adds `user_profiles` and an Admin record while preserving existing table rows/layouts. No firmware upgrade or network reset is needed. Restart the Pi dashboard service after source deployment, then refresh the browser page and reconnect.

To roll back, stop the service and restore the previous source before restarting. The older application can ignore the added profile table and continue using Admin's legacy configuration; retaining it preserves profile layouts for a future upgrade. Avoid replacing the database with an older snapshot merely to roll back code, as that would discard newer readings and edits. Retain private backups and deployment evidence outside Git.
