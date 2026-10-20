"""Gateway client, input validation and persistent event projection. Python 3.11+."""
import json
import re
import sqlite3
import threading
import time
import unicodedata
import urllib.error
import urllib.request
import uuid
from .dashboard import DashboardStore
from .network import Gateway, sample_received
from .commissioning import CommissioningStore, drive_commissioning
from .sensors import sensor_endpoint
from .plug_jobs import PlugStore,drive_plugs
from . import plugs
from .display import DisplayStore,drive_display,drive_clock
from .system import SystemStore, RETENTION_DAYS

OPS = {"permit_join", "discover", "read", "on_off", "bind", "configure_reporting", "read_reporting", "reporting_window", "write_display", "read_display", "sync_clock"}

class ConfigurationError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status

def validate_command(c):
    if not isinstance(c, dict) or not isinstance(c.get("op"), str) or c["op"] not in OPS:
        raise ValueError("unsupported op")
    op = c["op"]
    fields = {"op"}
    def integer(key, lo, hi):
        v = c.get(key)
        if type(v) is not int or not lo <= v <= hi:
            raise ValueError(f"{key} must be an integer {lo}..{hi}")
        fields.add(key)
    if op=='sync_clock':
        integer('unix_time',1577836800,4102444800);integer('utc_offset',-50400,50400)
    elif op == "permit_join":
        integer("seconds", 0, 180)
    else:
        if not isinstance(c.get("ieee"), str) or not re.fullmatch(r"[0-9a-fA-F]{16}", c["ieee"]):
            raise ValueError("ieee must be 16 hexadecimal digits")
        fields.add("ieee")
        if op != "discover":
            integer("endpoint", 1, 240)
        if op == "read":
            integer("cluster", 0, 65535)
            integer("attribute", 0, 65535)
            if c["cluster"] == 65535:
                raise ValueError("Signal strength is passive dashboard telemetry, not a Zigbee read.")
        if op in ("bind", "configure_reporting", "read_reporting", "reporting_window", "write_display", "read_display"):
            if not isinstance(c.get("request_id"),str) or not re.fullmatch('[0-9a-f-]{36}',c['request_id']):
                raise ValueError('request_id required')
            fields.add('request_id')
            if op == 'reporting_window':integer('seconds',0,120)
            else:
                integer('cluster',0,65535)
                allowed=(1,6,32,1026,1029) if op=='bind' else (64529,) if op in ('write_display','read_display') else (1,1026,1029)
                if c['cluster'] not in allowed:raise ValueError('unsupported cluster')
                if op in ('write_display','read_display'):
                    from .sensors import DISPLAY_FIELDS
                    integer('attribute',0,65535)
                    spec=next((v for v in DISPLAY_FIELDS.values() if v[0]==c['attribute']),None)
                    if not spec:raise ValueError('unsupported display attribute')
                    if op=='write_display':
                        integer('value',spec[2]*spec[4],spec[3]*spec[4])
                        if c['attribute']!=7 and c['value']%10:raise ValueError('display increment')
                elif op!='bind':
                    integer('attribute',0,65535)
                    if c['attribute'] not in ((32,33) if c['cluster']==1 else (0,)):raise ValueError('unsupported attribute')
                if op=='configure_reporting':
                    integer('min_interval',0,65534);integer('max_interval',1,65534)
                    integer('reportable_change',1,32767 if c['cluster']==1026 else 254 if c['cluster']==1 else 10000)
                    if c['min_interval']>c['max_interval']:raise ValueError('interval order')
        if op == "on_off":
            if type(c.get("state")) is not bool:
                raise ValueError("state must be boolean")
            fields.add("state")
    if set(c) != fields:
        raise ValueError("unexpected fields")
    return c

def normalize(cluster, attribute, data_type, raw, device=None, endpoint=None):
    if (cluster,attribute) in plugs.METRICS:
        return plugs.normalize(device or {},endpoint,cluster,attribute,data_type,raw)
    """Keep invalid ZCL sentinel values out of usable measurements."""
    if type(raw) not in (int,float):return None,None
    if cluster==1 and data_type==0x20:
        if attribute==33:return (raw/2,'%') if 0<=raw<=200 else (None,None)
        if attribute==32:return (raw/10,'V') if 0<=raw<255 else (None,None)
    if attribute != 0 or type(raw) not in (int, float):
        return None, None
    if cluster == 0x0402 and data_type == 0x29 and raw != -32768:
        return raw / 100, "°C"
    if cluster == 0x0405 and data_type == 0x21 and 0 <= raw <= 10000:
        return raw / 100, "%"
    if cluster == 0x0006 and data_type == 0x10 and raw in (0, 1):
        return bool(raw), "on/off"
    return None, None

class Store(DashboardStore, CommissioningStore, DisplayStore, PlugStore, SystemStore):
    def __init__(self, path):
        self.lock = threading.RLock()
        self._init_system(path)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS devices(ieee TEXT PRIMARY KEY, data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(boot TEXT, seq INTEGER, received REAL, data TEXT,
            PRIMARY KEY(boot,seq));
          CREATE TABLE IF NOT EXISTS cursor(id INTEGER PRIMARY KEY CHECK(id=1), boot TEXT, seq INTEGER);
          CREATE TABLE IF NOT EXISTS locations(id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT UNIQUE NOT NULL);
          CREATE TABLE IF NOT EXISTS device_locations(
            ieee TEXT PRIMARY KEY REFERENCES devices(ieee),
            location_id TEXT NOT NULL REFERENCES locations(id));
        ''')
        self.db.commit()
        self._init_dashboard()
        self._init_commissioning()
        self._init_display()
        self._init_plugs()
        self.db.execute('CREATE INDEX IF NOT EXISTS event_retention_time ON events(received)')
        self.db.execute('CREATE INDEX IF NOT EXISTS measurement_retention_time ON measurements(received)')
        self.db.execute('CREATE INDEX IF NOT EXISTS plug_discontinuity_retention_time ON plug_discontinuities(received)')
        self.db.execute('CREATE TABLE IF NOT EXISTS gateway_bindings(config_key TEXT PRIMARY KEY,identity TEXT NOT NULL,url TEXT NOT NULL)')
        self.db.commit()
    def cursor(self):
        with self.lock:
            row = self.db.execute("SELECT boot,seq FROM cursor WHERE id=1").fetchone()
            return row if row else ("", 0)
    def _get(self, ieee):
        row = self.db.execute("SELECT data FROM devices WHERE ieee=?", (ieee,)).fetchone()
        return json.loads(row[0]) if row else {"ieee": ieee, "endpoints": {}, "attributes": {}}
    def _put(self, d):
        new = not self.db.execute("SELECT 1 FROM devices WHERE ieee=?", (d["ieee"],)).fetchone()
        self.db.execute("INSERT INTO devices VALUES(?,?) ON CONFLICT(ieee) DO UPDATE SET data=excluded.data",
                        (d["ieee"], json.dumps(d)))
        if new:
            self._bump_revision()
    def sync_devices(self, items):
        with self.lock, self.db:
            self._sync_devices(items)
    def _sync_devices(self, items):
        for item in items:
            d = self._get(item["ieee"])
            d.update(item)
            self._put(d)
    def ingest(self, boot, events, next_seq, devices=None, gap_start=None, gap_reason="history_gap"):
        with self.lock, self.db:
            if gap_start is not None:
                self.db.execute("INSERT INTO ingestion_gaps(start,end,reason) VALUES(?,?,?)", (gap_start, time.time(), gap_reason))
            for e in events:
                received = time.time()
                inserted = self.db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?)",
                    (boot, e["seq"], received, json.dumps(e))).rowcount
                if not inserted or not e.get("ieee"):
                    continue
                self.commissioning_event(e,received)
                self.display_event(e,received)
                self.plug_event(boot,e,received)
                self._record_measurement(boot, e, received)
                self._record_signal(boot, e, received)
                d = self._get(e["ieee"])
                d["nwk"] = e["nwk"]
                if e["type"] in ("announce","attribute","check_in","zcl_response") or (e["type"] in ("endpoint","discovery") and e.get("ok")) or (e["type"]=="commissioning" and e.get("phase")=="response"):
                    d["last_seen"] = received
                    d["last_contact"] = received
                if e["type"] == "announce":
                    d["active"] = True
                    if "capability" in e:d["capability"]=e["capability"]
                if e["type"] == "leave":
                    d["active"] = False
                if e["type"] == "endpoint" and e.get("ok"):
                    d["endpoints"][str(e["endpoint"])] = {k: e[k] for k in
                        ("profile_id", "device_id", "input_clusters", "output_clusters")}
                if e["type"] == "attribute":
                    self._plug_counter(boot,e,received,d)
                    value, unit = normalize(e["cluster"], e["attribute"], e["data_type"], e.get("raw"),d,e["endpoint"])
                    e = dict(e, value=value, unit=unit, source_boot=boot, received=sample_received(e,received))
                    d["attributes"][f'{e["endpoint"]}:{e["cluster"]}:{e["attribute"]}'] = e
                self._put(d)
            # Current registry wins over historical membership/address events.
            # Commit it with the events and cursor so readers see one projection.
            if devices is not None:
                self._sync_devices(devices)
            self.db.execute("INSERT OR REPLACE INTO cursor VALUES(1,?,?)", (boot, next_seq))
            self.db.execute("INSERT OR REPLACE INTO ingestion_state VALUES(1,?)", (time.time(),))
    def snapshot(self):
        with self.lock:
            return [dict(json.loads(row[0]), location_id=row[1], location_name=row[2]) for row in self.db.execute(
                "SELECT d.data,l.id,l.name FROM devices d LEFT JOIN device_locations a ON a.ieee=d.ieee "
                "LEFT JOIN locations l ON l.id=a.location_id ORDER BY d.ieee")]
    def locations(self):
        with self.lock:
            return [dict(id=row[0], name=row[1], device_count=row[2]) for row in self.db.execute(
                "SELECT l.id,l.name,COUNT(a.ieee) FROM locations l LEFT JOIN device_locations a "
                "ON a.location_id=l.id GROUP BY l.id ORDER BY l.name_key,l.id")]
    def save_location(self, name, location_id=None):
        if not isinstance(name, str):
            raise ConfigurationError("name must be a string")
        if not 1 <= len(name) <= 80:
            raise ConfigurationError("name must contain 1..80 characters")
        name = unicodedata.normalize("NFC", name.strip())
        if not 1 <= len(name) <= 80 or any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in name):
            raise ConfigurationError("name must contain 1..80 visible characters on one line")
        key = unicodedata.normalize("NFKC", name).casefold()
        with self.lock, self.db:
            if location_id is not None and not self.db.execute("SELECT 1 FROM locations WHERE id=?", (location_id,)).fetchone():
                raise ConfigurationError("location not found", 404)
            duplicate = self.db.execute("SELECT id FROM locations WHERE name_key=?", (key,)).fetchone()
            if duplicate and duplicate[0] != location_id:
                raise ConfigurationError("a location with that name already exists", 409)
            if location_id is None:
                if self.db.execute("SELECT COUNT(*) FROM locations").fetchone()[0] >= 50:
                    raise ConfigurationError("location limit of 50 reached", 409)
                location_id = str(uuid.uuid4())
                self.db.execute("INSERT INTO locations VALUES(?,?,?)", (location_id, name, key))
            else:
                self.db.execute("UPDATE locations SET name=?,name_key=? WHERE id=?", (name, key, location_id))
            self._bump_revision()
            return next(location for location in self.locations() if location["id"] == location_id)
    def delete_location(self, location_id):
        with self.lock, self.db:
            if not self.db.execute("SELECT 1 FROM locations WHERE id=?", (location_id,)).fetchone():
                raise ConfigurationError("location not found", 404)
            if self.db.execute("SELECT 1 FROM device_locations WHERE location_id=?", (location_id,)).fetchone():
                raise ConfigurationError("move or unassign devices before deleting this location", 409)
            self.db.execute("DELETE FROM locations WHERE id=?", (location_id,))
            self._bump_revision()
    def assign_location(self, ieee, location_id):
        if location_id is not None and not isinstance(location_id, str):
            raise ConfigurationError("location_id must be a string or null")
        with self.lock, self.db:
            if not self.db.execute("SELECT 1 FROM devices WHERE ieee=?", (ieee,)).fetchone():
                raise ConfigurationError("device not found", 404)
            if location_id is None:
                self.db.execute("DELETE FROM device_locations WHERE ieee=?", (ieee,))
            else:
                if not self.db.execute("SELECT 1 FROM locations WHERE id=?", (location_id,)).fetchone():
                    raise ConfigurationError("location not found", 404)
                self.db.execute("INSERT INTO device_locations VALUES(?,?) ON CONFLICT(ieee) "
                                "DO UPDATE SET location_id=excluded.location_id", (ieee, location_id))
            self._bump_revision()
            return {"ieee": ieee, "location_id": location_id}
    def history(self, limit=100):
        with self.lock:
            return [dict(json.loads(row[0]), received=row[1], boot_id=row[2]) for row in
                self.db.execute("SELECT data,received,boot FROM events ORDER BY received DESC LIMIT ?", (limit,))]
    def prune(self, days):
        with self.lock, self.db:
            self._prune_signal(time.time(), days)
            self.db.execute("DELETE FROM events WHERE received < ?", (time.time()-days*86400,))
            self.db.execute("DELETE FROM measurements WHERE received < ?", (time.time()-days*86400,))
            self.db.execute("DELETE FROM ingestion_gaps WHERE end < ?", (time.time()-days*86400,))
            self.db.execute("DELETE FROM plug_discontinuities WHERE received < ?", (time.time()-days*86400,))
    def close(self):
        self.db.close()

class Poller:
    def __init__(self, gateway, store):
        self.gateway, self.store = gateway, store
        if isinstance(gateway, Gateway):gateway.attach_store(store)
        self.status = {"connected": False, "error": "Waiting for gateway", "gap": False}
        self.radio = {"status": "unsupported", "source": "gateway_local_tables", "neighbors": [], "routes": [], "route_records": []}
        self._radio_polled_at = 0
        self.stop = threading.Event()
    def _refresh_radio(self):
        now = time.time()
        if now - self._radio_polled_at < 30:
            return
        self._radio_polled_at = now
        try:
            snapshot = self.gateway.request("/api/v1/radio")
            self.radio = dict(snapshot, status="available", source=snapshot.get("scope", "gateway_radio_snapshot"), observed_at=now, error=None)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self.radio = {"status": "unsupported", "source": "gateway_local_tables",
                    "neighbors": [], "routes": [], "route_records": [], "observed_at": now,
                    "error": "Gateway firmware does not expose radio snapshots."}
            else:
                self._radio_failed(now, type(e).__name__)
        except Exception as e:
            self._radio_failed(now, type(e).__name__)
    def _radio_failed(self, now, error):
        self.radio = dict(self.radio, status="stale" if self.radio.get("status") == "available" else "unavailable",
            last_attempt_at=now, error=error)
    def once(self):
        h = self.gateway.request("/api/v1/health")
        health_received = time.time()
        boot, seq = self.store.cursor()
        changed = h["boot_id"] != boot
        if changed:
            seq = 0
        batch = self.gateway.request(f"/api/v1/events?after={seq}")
        # Fetch the registry after events so its membership/address state is newer.
        registry = self.gateway.request("/api/v1/devices")
        if batch["boot_id"] != h["boot_id"] or registry["boot_id"] != h["boot_id"]:
            raise RuntimeError("gateway restarted during poll; retrying")
        # Preserve source ages when draining events buffered during an outage.
        if type(h.get('uptime_ms')) is int:
            batch['events']=[dict(e,observed_at_estimate=max(0,health_received-max(0,h['uptime_ms']-e['uptime_ms'])/1000))
                if type(e.get('uptime_ms')) is int and e['uptime_ms']>=0 else e for e in batch['events']]
        previous_poll = self.status.get("last_poll") or self.store.last_ingestion()
        if previous_poll is None and batch.get("gap"):
            with self.store.lock:
                previous_poll = self.store.db.execute("SELECT MAX(received) FROM events").fetchone()[0]
        interrupted = previous_poll is not None and (not self.status.get("connected") or batch.get("gap") or (changed and bool(boot)))
        self.store.ingest(batch["boot_id"], batch["events"], batch["next_seq"], registry["devices"],
            gap_start=previous_poll if interrupted else None,
            gap_reason="gateway_restart" if changed else "history_gap" if batch.get("gap") else "connection_interrupted")
        self.status = dict(h, connected=True, error=None,
            gap=bool(batch.get("gap") or self.status.get("gap")), last_poll=time.time())
        self._refresh_radio()
        drive_commissioning(self.store,self.gateway,h)
        drive_display(self.store,self.gateway,h)
        drive_clock(self,h)
        drive_plugs(self.store,self.gateway,h)
        return batch["next_seq"] < batch["latest_seq"]
    def run(self):
        cycles = 0
        while not self.stop.is_set():
            interval = 2
            try:
                interval = .1 if self.once() else 2
                cycles += 1
                if cycles % 1800 == 0:
                    self.store.prune(RETENTION_DAYS)
            except Exception as e:
                # Avoid logging URLs/tokens or credentials from upstream failures.
                self.status = dict(self.status, connected=False, error=type(e).__name__)
                interval = 5
            self.stop.wait(interval)
