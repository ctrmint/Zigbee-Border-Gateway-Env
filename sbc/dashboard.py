"""Persistent dashboard configuration and indexed measurement history."""
import base64
import hashlib
import hmac
import json
import math
import re
import secrets
import time
import unicodedata

MEASUREMENTS = {(1026, 0): ("Temperature", "°C"), (1029, 0): ("Humidity", "%"),
                (6, 0): ("Reported state", "on/off")}
RANGES = (3600, 21600, 86400, 604800, 2592000)


class DashboardError(ValueError):
    def __init__(self, message, status=422, code="validation_failed", path=""):
        super().__init__(message)
        self.status, self.code, self.path = status, code, path


def text(value, path, maximum=80):
    if not isinstance(value, str):
        raise DashboardError("A text value is required.", path=path)
    value = unicodedata.normalize("NFC", value.strip())
    if not 1 <= len(value) <= maximum or any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in value):
        raise DashboardError(f"Use 1–{maximum} visible characters on one line.", path=path)
    return value


def source_supported(device, endpoint, cluster, attribute):
    return (cluster, attribute) in MEASUREMENTS and (
        cluster in device.get("endpoints", {}).get(str(endpoint), {}).get("input_clusters", []) or
        f"{endpoint}:{cluster}:{attribute}" in device.get("attributes", {}))


class DashboardStore:
    def _init_dashboard(self):
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS dashboard_config(
            id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, data TEXT NOT NULL,
            cursor_key TEXT NOT NULL, history_migrated INTEGER NOT NULL DEFAULT 0);
          CREATE TABLE IF NOT EXISTS device_settings(ieee TEXT PRIMARY KEY REFERENCES devices(ieee),
            name TEXT, freshness_seconds INTEGER NOT NULL DEFAULT 3600);
          CREATE TABLE IF NOT EXISTS measurements(
            id INTEGER PRIMARY KEY AUTOINCREMENT, boot TEXT NOT NULL, seq INTEGER NOT NULL,
            ieee TEXT NOT NULL, endpoint INTEGER NOT NULL, cluster INTEGER NOT NULL,
            attribute INTEGER NOT NULL, received REAL NOT NULL, value REAL, unit TEXT,
            UNIQUE(boot,seq));
          CREATE INDEX IF NOT EXISTS measurement_source_time
            ON measurements(ieee,endpoint,cluster,attribute,received,id);
          CREATE TABLE IF NOT EXISTS ingestion_gaps(
            id INTEGER PRIMARY KEY, start REAL NOT NULL, end REAL NOT NULL, reason TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS gap_time ON ingestion_gaps(end,start);
          CREATE TABLE IF NOT EXISTS ingestion_state(id INTEGER PRIMARY KEY CHECK(id=1), received REAL NOT NULL);
        ''')
        with self.db:
            created = self.db.execute("INSERT OR IGNORE INTO dashboard_config(id,revision,data,cursor_key) VALUES(1,1,?,?)",
                (json.dumps({"title": "Home", "temperature_unit": "celsius", "widgets": []}), secrets.token_hex(32))).rowcount
            if created:
                widgets = []
                for device in self.snapshot():
                    if not device["location_id"]: continue
                    for endpoint in sorted(map(int, device["endpoints"])):
                        for (cluster, attribute), (label, _) in MEASUREMENTS.items():
                            if not source_supported(device, endpoint, cluster, attribute): continue
                            for kind in ("numeric", "chart"):
                                if len(widgets) >= 100: break
                                widgets.append({"id": "w-"+secrets.token_hex(12), "type": kind,
                                    "title": label+(" history" if kind == "chart" else ""),
                                    "source": {"ieee": device["ieee"], "endpoint": endpoint, "cluster": cluster, "attribute": attribute},
                                    "position": len(widgets), "time_range": 86400})
                self.db.execute("UPDATE dashboard_config SET data=? WHERE id=1",
                    (json.dumps({"title": "Home", "temperature_unit": "celsius", "widgets": widgets}),))
            if not self.db.execute("SELECT history_migrated FROM dashboard_config WHERE id=1").fetchone()[0]:
                for boot, received, data in self.db.execute("SELECT boot,received,data FROM events ORDER BY received,seq"):
                    self._record_measurement(boot, json.loads(data), received)
                self.db.execute("UPDATE dashboard_config SET history_migrated=1 WHERE id=1")

    def _record_measurement(self, boot, event, received):
        if event.get("type") != "attribute" or not event.get("ieee"):
            return
        from .core import normalize
        cluster, attribute = event.get("cluster"), event.get("attribute")
        if (cluster, attribute) not in MEASUREMENTS:
            return
        value, unit = normalize(cluster, attribute, event.get("data_type"), event.get("raw"))
        if value is not None and not math.isfinite(value):
            value = None
        self.db.execute("INSERT OR IGNORE INTO measurements(boot,seq,ieee,endpoint,cluster,attribute,received,value,unit) "
            "VALUES(?,?,?,?,?,?,?,?,?)", (boot, event["seq"], event["ieee"].lower(), event["endpoint"], cluster,
                attribute, received, value, unit or MEASUREMENTS[(cluster, attribute)][1]))

    def _bump_revision(self):
        self.db.execute("UPDATE dashboard_config SET revision=revision+1 WHERE id=1")

    def last_ingestion(self):
        with self.lock:
            row = self.db.execute("SELECT received FROM ingestion_state WHERE id=1").fetchone()
            return row[0] if row else None

    def configuration_document(self):
        with self.lock:
            revision, data = self.db.execute("SELECT revision,data FROM dashboard_config WHERE id=1").fetchone()
            settings = {r[0]: r[1:] for r in self.db.execute("SELECT ieee,name,freshness_seconds FROM device_settings")}
            devices = {}
            for d in self.snapshot():
                name, freshness = settings.get(d["ieee"], (None, 3600))
                devices[d["ieee"]] = {"location_id": d["location_id"], "freshness_seconds": freshness}
                if name:
                    devices[d["ieee"]]["name"] = name
            return {"schema_version": 1, "revision": revision,
                "locations": [{"id": l["id"], "name": l["name"]} for l in self.locations()],
                "devices": devices, "dashboard": json.loads(data)}

    def replace_configuration(self, body, expected):
        with self.lock, self.db:
            self.db.execute("BEGIN IMMEDIATE")
            revision = self.db.execute("SELECT revision FROM dashboard_config WHERE id=1").fetchone()[0]
            if expected != f'"configuration-{revision}"':
                raise DashboardError("Configuration changed. Reload before saving.", 412, "configuration_conflict")
            if not isinstance(body, dict) or set(body) != {"locations", "devices", "dashboard"}:
                raise DashboardError("Provide locations, devices and dashboard only.")
            locations, overrides, dashboard = body["locations"], body["devices"], body["dashboard"]
            if not isinstance(locations, list) or len(locations) > 50:
                raise DashboardError("At most 50 locations are allowed.", path="locations")
            current_ids = {l["id"] for l in self.locations()}
            names, normalized_locations = set(), {}
            for index, location in enumerate(locations):
                path = f"locations[{index}]"
                if not isinstance(location, dict) or set(location) != {"id", "name"} or not isinstance(location.get("id"), str) or location.get("id") not in current_ids:
                    raise DashboardError("Use an existing location ID; create locations through Setup.", path=path)
                name = text(location["name"], path + ".name")
                key = unicodedata.normalize("NFKC", name).casefold()
                if location["id"] in normalized_locations or key in names:
                    raise DashboardError("Location IDs and names must be unique.", path=path)
                normalized_locations[location["id"]] = (name, key)
                names.add(key)
            known = {d["ieee"]: d for d in self.snapshot()}
            if not isinstance(overrides, dict) or len(overrides) > 50:
                raise DashboardError("At most 50 device settings are allowed.", path="devices")
            normalized_devices = {}
            for ieee, setting in overrides.items():
                path = "devices." + ieee
                if ieee not in known or not isinstance(setting, dict) or set(setting) - {"name", "location_id", "freshness_seconds"}:
                    raise DashboardError("Use a known device and supported settings.", path=path)
                location_id = setting.get("location_id")
                if location_id is not None and (not isinstance(location_id, str) or location_id not in normalized_locations):
                    raise DashboardError("Select an existing location or leave unassigned.", path=path + ".location_id")
                freshness = setting.get("freshness_seconds", 3600)
                if type(freshness) is not int or not 60 <= freshness <= 604800:
                    raise DashboardError("Freshness must be 60–604800 seconds.", path=path + ".freshness_seconds")
                normalized_devices[ieee] = {"location_id": location_id, "freshness_seconds": freshness}
                if "name" in setting:
                    normalized_devices[ieee]["name"] = text(setting["name"], path + ".name")
            if not isinstance(dashboard, dict) or set(dashboard) != {"title", "temperature_unit", "widgets"}:
                raise DashboardError("Provide title, temperature_unit and widgets.", path="dashboard")
            title = text(dashboard["title"], "dashboard.title")
            if dashboard["temperature_unit"] not in ("celsius", "fahrenheit"):
                raise DashboardError("Choose Celsius or Fahrenheit.", path="dashboard.temperature_unit")
            widgets = dashboard["widgets"]
            if not isinstance(widgets, list) or len(widgets) > 100:
                raise DashboardError("At most 100 widgets are allowed.", path="dashboard.widgets")
            ids, positions, normalized_widgets = set(), set(), []
            for index, widget in enumerate(widgets):
                path = f"dashboard.widgets[{index}]"
                if not isinstance(widget, dict) or set(widget) != {"id", "type", "title", "source", "position", "time_range"}:
                    raise DashboardError("Unsupported widget fields.", path=path)
                wid, kind, source = widget["id"], widget["type"], widget["source"]
                if not isinstance(wid, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,63}", wid) or wid in ids:
                    raise DashboardError("Use a unique widget ID.", path=path + ".id")
                if kind not in ("numeric", "chart"):
                    raise DashboardError("Choose a numeric reading or chart.", path=path + ".type")
                position = widget["position"]
                if type(position) is not int or not 0 <= position <= 99 or position in positions:
                    raise DashboardError("Use unique widget positions from 0 to 99.", path=path + ".position")
                if type(widget["time_range"]) is not int or widget["time_range"] not in RANGES:
                    raise DashboardError("Choose a supported chart time range.", path=path + ".time_range")
                if not isinstance(source, dict) or set(source) != {"ieee", "endpoint", "cluster", "attribute"}:
                    raise DashboardError("Select a device endpoint measurement.", path=path + ".source")
                ieee = source.get("ieee")
                if not isinstance(ieee, str) or not re.fullmatch(r"[0-9a-f]{16}", ieee) or ieee not in known:
                    raise DashboardError("Select a known device.", path=path + ".source.ieee")
                for key, minimum, maximum in (("endpoint", 1, 240), ("cluster", 0, 65535), ("attribute", 0, 65535)):
                    if type(source[key]) is not int or not minimum <= source[key] <= maximum:
                        raise DashboardError("Invalid measurement identifier.", path=path + ".source." + key)
                if not source_supported(known[ieee], source["endpoint"], source["cluster"], source["attribute"]):
                    raise DashboardError("This measurement is not available on the selected endpoint.", path=path + ".source")
                normalized_widgets.append(dict(widget, title=text(widget["title"], path + ".title"), source=dict(source)))
                ids.add(wid); positions.add(position)
            # All validation precedes writes; atomically replace metadata, assignments and layout.
            self.db.execute("DELETE FROM device_locations")
            self.db.execute("DELETE FROM device_settings")
            self.db.execute("DELETE FROM locations")
            for lid, (name, key) in normalized_locations.items():
                self.db.execute("INSERT INTO locations VALUES(?,?,?)", (lid, name, key))
            for ieee, setting in normalized_devices.items():
                self.db.execute("INSERT INTO device_settings VALUES(?,?,?)", (ieee, setting.get("name"), setting["freshness_seconds"]))
                if setting["location_id"]:
                    self.db.execute("INSERT INTO device_locations VALUES(?,?)", (ieee, setting["location_id"]))
            value = {"title": title, "temperature_unit": dashboard["temperature_unit"], "widgets": normalized_widgets}
            self.db.execute("UPDATE dashboard_config SET data=?,revision=revision+1 WHERE id=1", (json.dumps(value),))
            return self.configuration_document()

    def device_views(self):
        with self.lock:
            config = self.configuration_document()
            views = []
            now = time.time()
            for d in self.snapshot():
                setting = config["devices"][d["ieee"]]
                measurements = []
                endpoints = set(map(int, d["endpoints"])) | {a["endpoint"] for a in d["attributes"].values()}
                for endpoint in sorted(endpoints):
                    for (cluster, attribute), (label, unit) in MEASUREMENTS.items():
                        if not source_supported(d, endpoint, cluster, attribute):
                            continue
                        a = d["attributes"].get(f"{endpoint}:{cluster}:{attribute}", {})
                        value, received = a.get("value"), a.get("received")
                        quality = "missing" if not a else "invalid" if value is None else "stale" if now - received > setting["freshness_seconds"] else "valid"
                        measurements.append({"endpoint": endpoint, "cluster": cluster, "attribute": attribute,
                            "label": label, "value": value, "unit": unit, "received_at": received, "quality": quality})
                model = next((a.get("raw") for a in d["attributes"].values() if a["cluster"] == 0 and a["attribute"] == 5 and isinstance(a.get("raw"), str)), None)
                views.append({"ieee": d["ieee"], "name": setting.get("name") or model or d["ieee"],
                    "location_id": d["location_id"], "registered": d.get("active", False),
                    "discovery": "partial" if d["endpoints"] else "unknown", "freshness_seconds": setting["freshness_seconds"],
                    "measurements": measurements})
            return {"devices": views}

    def measurement_history(self, query):
        required = {"ieee", "endpoint", "cluster", "attribute", "from", "to"}
        if not required <= query.keys() or query.keys() - required - {"limit", "cursor"}:
            raise DashboardError("Provide a measurement and bounded time range.", 400, "invalid_query")
        ieee = query["ieee"]
        if not re.fullmatch(r"[0-9a-fA-F]{16}", ieee):
            raise DashboardError("Invalid device identity.", 400, "invalid_query")
        identity = [ieee.lower()]
        for key, low, high in (("endpoint", 1, 240), ("cluster", 0, 65535), ("attribute", 0, 65535), ("limit", 1, 500)):
            s = query.get(key, "100")
            if not re.fullmatch(r"[0-9]{1,10}", s) or not low <= int(s) <= high:
                raise DashboardError("Invalid " + key + ".", 400, "invalid_query")
            if key == "limit": limit = int(s)
            else: identity.append(int(s))
        try: start, end = float(query["from"]), float(query["to"])
        except ValueError: raise DashboardError("Invalid time range.", 400, "invalid_query")
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end or end-start > 31*86400:
            raise DashboardError("Time range must be positive and at most 31 days.", 400, "invalid_query")
        filters = identity + [start, end]
        with self.lock:
            key = self.db.execute("SELECT cursor_key FROM dashboard_config WHERE id=1").fetchone()[0].encode()
            after_time, after_id = -1, 0
            if "cursor" in query:
                try:
                    payload, signature = query["cursor"].split(".")
                    expected = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
                    if not hmac.compare_digest(signature, expected): raise ValueError()
                    data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
                    if data["filters"] != filters or type(data["id"]) is not int or data["id"] < 1: raise ValueError()
                    after_time, after_id = data["time"], data["id"]
                    if type(after_time) not in (int, float) or not math.isfinite(after_time) or not start <= after_time <= end: raise ValueError()
                except (ValueError, KeyError, TypeError, UnicodeError):
                    raise DashboardError("Cursor does not match this history query.", 400, "invalid_cursor")
            rows = self.db.execute("SELECT id,received,value,unit FROM measurements WHERE ieee=? AND endpoint=? AND cluster=? "
                "AND attribute=? AND received>=? AND received<=? AND (received>? OR (received=? AND id>?)) "
                "ORDER BY received,id LIMIT ?", (*filters, after_time, after_time, after_id, limit+1)).fetchall()
            more = len(rows) > limit; rows = rows[:limit]
            items = [{"id": r[0], "received_at": r[1], "value": bool(r[2]) if identity[2] == 6 and r[2] is not None else r[2],
                "unit": r[3], "quality": "invalid" if r[2] is None else "valid"} for r in rows]
            cursor = None
            if more:
                payload = base64.urlsafe_b64encode(json.dumps({"filters": filters, "time": rows[-1][1], "id": rows[-1][0]}, separators=(",", ":")).encode()).decode().rstrip("=")
                cursor = payload + "." + hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
            gap_rows = self.db.execute("SELECT start,end,reason FROM ingestion_gaps WHERE end>=? AND start<=? ORDER BY start LIMIT 501", (start, end)).fetchall()
            gaps = [{"from": r[0], "to": r[1], "reason": r[2]} for r in gap_rows[:500]]
            return {"items": items, "next_cursor": cursor, "gaps": gaps, "gaps_truncated": len(gap_rows)>500}
