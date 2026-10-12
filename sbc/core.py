"""Gateway client, input validation and persistent event projection. Python 3.11+."""
import json
import re
import sqlite3
import threading
import time
import urllib.request

OPS = {"permit_join", "discover", "read", "on_off"}

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
    if op == "permit_join":
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
        if op == "on_off":
            if type(c.get("state")) is not bool:
                raise ValueError("state must be boolean")
            fields.add("state")
    if set(c) != fields:
        raise ValueError("unexpected fields")
    return c

def normalize(cluster, attribute, data_type, raw):
    """Keep invalid ZCL sentinel values out of usable measurements."""
    if attribute != 0 or type(raw) not in (int, float):
        return None, None
    if cluster == 0x0402 and data_type == 0x29 and raw != -32768:
        return raw / 100, "°C"
    if cluster == 0x0405 and data_type == 0x21 and 0 <= raw <= 10000:
        return raw / 100, "%"
    if cluster == 0x0006 and data_type == 0x10 and raw in (0, 1):
        return bool(raw), "on/off"
    return None, None

class Gateway:
    def __init__(self, url, token):
        self.url, self.token = url.rstrip("/"), token
    def request(self, path, data=None):
        req = urllib.request.Request(self.url + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Authorization": "Bearer " + self.token, "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript('''
          CREATE TABLE IF NOT EXISTS devices(ieee TEXT PRIMARY KEY, data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS events(boot TEXT, seq INTEGER, received REAL, data TEXT,
            PRIMARY KEY(boot,seq));
          CREATE TABLE IF NOT EXISTS cursor(id INTEGER PRIMARY KEY CHECK(id=1), boot TEXT, seq INTEGER);
        ''')
        self.db.commit()
    def cursor(self):
        with self.lock:
            row = self.db.execute("SELECT boot,seq FROM cursor WHERE id=1").fetchone()
            return row if row else ("", 0)
    def _get(self, ieee):
        row = self.db.execute("SELECT data FROM devices WHERE ieee=?", (ieee,)).fetchone()
        return json.loads(row[0]) if row else {"ieee": ieee, "endpoints": {}, "attributes": {}}
    def _put(self, d):
        self.db.execute("INSERT OR REPLACE INTO devices VALUES(?,?)", (d["ieee"], json.dumps(d)))
    def sync_devices(self, items):
        with self.lock, self.db:
            self._sync_devices(items)
    def _sync_devices(self, items):
        for item in items:
            d = self._get(item["ieee"])
            d.update(item)
            self._put(d)
    def ingest(self, boot, events, next_seq, devices=None):
        with self.lock, self.db:
            for e in events:
                inserted = self.db.execute("INSERT OR IGNORE INTO events VALUES(?,?,?,?)",
                    (boot, e["seq"], time.time(), json.dumps(e))).rowcount
                if not inserted or not e.get("ieee"):
                    continue
                d = self._get(e["ieee"])
                d["nwk"] = e["nwk"]
                d["last_seen"] = time.time()
                if e["type"] == "announce":
                    d["active"] = True
                if e["type"] == "leave":
                    d["active"] = False
                if e["type"] == "endpoint" and e.get("ok"):
                    d["endpoints"][str(e["endpoint"])] = {k: e[k] for k in
                        ("profile_id", "device_id", "input_clusters", "output_clusters")}
                if e["type"] == "attribute":
                    value, unit = normalize(e["cluster"], e["attribute"], e["data_type"], e.get("raw"))
                    e = dict(e, value=value, unit=unit, received=time.time())
                    d["attributes"][f'{e["endpoint"]}:{e["cluster"]}:{e["attribute"]}'] = e
                self._put(d)
            # Current registry wins over historical membership/address events.
            # Commit it with the events and cursor so readers see one projection.
            if devices is not None:
                self._sync_devices(devices)
            self.db.execute("INSERT OR REPLACE INTO cursor VALUES(1,?,?)", (boot, next_seq))
    def snapshot(self):
        with self.lock:
            return [json.loads(row[0]) for row in self.db.execute("SELECT data FROM devices ORDER BY ieee")]
    def history(self, limit=100):
        with self.lock:
            return [dict(json.loads(row[0]), received=row[1], boot_id=row[2]) for row in
                self.db.execute("SELECT data,received,boot FROM events ORDER BY received DESC LIMIT ?", (limit,))]
    def prune(self, days):
        with self.lock, self.db:
            self.db.execute("DELETE FROM events WHERE received < ?", (time.time()-days*86400,))
    def close(self):
        self.db.close()

class Poller:
    def __init__(self, gateway, store):
        self.gateway, self.store = gateway, store
        self.status = {"connected": False, "error": "Waiting for gateway", "gap": False}
        self.stop = threading.Event()
    def once(self):
        h = self.gateway.request("/api/v1/health")
        boot, seq = self.store.cursor()
        changed = h["boot_id"] != boot
        if changed:
            seq = 0
        batch = self.gateway.request(f"/api/v1/events?after={seq}")
        # Fetch the registry after events so its membership/address state is newer.
        registry = self.gateway.request("/api/v1/devices")
        if batch["boot_id"] != h["boot_id"] or registry["boot_id"] != h["boot_id"]:
            raise RuntimeError("gateway restarted during poll; retrying")
        self.store.ingest(batch["boot_id"], batch["events"], batch["next_seq"], registry["devices"])
        self.status = dict(h, connected=True, error=None,
            gap=bool(batch.get("gap") or self.status.get("gap")), last_poll=time.time())
        return batch["next_seq"] < batch["latest_seq"]
    def run(self):
        cycles = 0
        while not self.stop.is_set():
            interval = 2
            try:
                interval = .1 if self.once() else 2
                cycles += 1
                if cycles % 1800 == 0:
                    self.store.prune(30)
            except Exception as e:
                # Avoid logging URLs/tokens or credentials from upstream failures.
                self.status = dict(self.status, connected=False, error=type(e).__name__)
                interval = 5
            self.stop.wait(interval)
