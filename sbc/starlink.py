"""Read-only Starlink router and dish telemetry over the local gRPC API."""
import ipaddress
import json
import math
import threading
import time

POLL_SECONDS = 60
RPC_TIMEOUT_SECONDS = 3
HISTORY_DAYS = 60
HISTORY_LIMIT = 500
MAX_HISTORY_ROWS = 90000
DEFAULT_DISH_HOST = "192.168.100.1"
DEFAULT_DISH_PORT = 9200
PRIVATE_V4 = tuple(map(ipaddress.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")))


class StarlinkUnavailable(Exception):
    code = "unavailable"


class StarlinkUnsupported(Exception):
    code = "unsupported"


def validate_target(host, port):
    if not isinstance(host, str) or not host or len(host) > 45 or host != host.strip():
        raise ValueError("Enter a private IPv4 address for the Starlink router.")
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError("Enter a private IPv4 address for the Starlink router.") from exc
    if address.version != 4 or not any(address in network for network in PRIVATE_V4):
        raise ValueError("The Starlink router must be addressed on a private IPv4 network.")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("The gRPC port must be an integer from 1 to 65535.")
    return host, port


def normalize_diagnostics(diagnostics):
    """Select bounded, non-identifying fields used by the dashboard."""
    networks = []
    for network in list(getattr(diagnostics, "networks", ()))[:32]:
        ipv6 = [str(value)[:80] for value in list(getattr(network, "ipv6", ()))[:8]]
        networks.append({
            "domain": str(getattr(network, "domain", ""))[:32],
            "ipv4": str(getattr(network, "ipv4", ""))[:64],
            "ipv6": ipv6,
            "clients_ethernet": _count(network, "clients_ethernet"),
            "clients_2ghz": _count(network, "clients_2ghz"),
            "clients_5ghz": _count(network, "clients_5ghz"),
        })
    return {
        "hardware_version": str(getattr(diagnostics, "hardware_version", ""))[:128] or None,
        "software_version": str(getattr(diagnostics, "software_version", ""))[:128] or None,
        "networks": networks,
    }


def _count(network, field):
    value = getattr(network, field, None)
    return value if type(value) is int and 0 <= value <= 100000 else None


def validate_snapshot(value):
    if not isinstance(value, dict) or set(value) != {"hardware_version", "software_version", "networks"}:
        raise StarlinkUnavailable("invalid_response")
    for field in ("hardware_version", "software_version"):
        if value[field] is not None and (not isinstance(value[field], str) or len(value[field]) > 128):
            raise StarlinkUnavailable("invalid_response")
    if not isinstance(value["networks"], list) or len(value["networks"]) > 32:
        raise StarlinkUnavailable("invalid_response")
    expected = {"domain", "ipv4", "ipv6", "clients_ethernet", "clients_2ghz", "clients_5ghz"}
    for network in value["networks"]:
        if not isinstance(network, dict) or set(network) != expected:
            raise StarlinkUnavailable("invalid_response")
        if any(not isinstance(network[key], str) or len(network[key]) > max_length
               for key, max_length in (("domain", 32), ("ipv4", 64))):
            raise StarlinkUnavailable("invalid_response")
        if not isinstance(network["ipv6"], list) or len(network["ipv6"]) > 8 or any(
                not isinstance(prefix, str) or len(prefix) > 80 for prefix in network["ipv6"]):
            raise StarlinkUnavailable("invalid_response")
        for key in ("clients_ethernet", "clients_2ghz", "clients_5ghz"):
            count = network[key]
            if count is not None and (type(count) is not int or not 0 <= count <= 100000):
                raise StarlinkUnavailable("invalid_response")
    return value


def normalize_dish_status(status):
    """Return selected service-performance fields, excluding dish identity/location."""
    state = getattr(status, "state", None) if status.HasField("state") else None
    if state is not None:
        state = {0: "UNKNOWN", 1: "CONNECTED", 2: "SEARCHING", 3: "BOOTING"}.get(
            int(state), "OTHER")
    obstruction = getattr(status, "obstruction_stats", None)
    fraction = None
    currently = None
    if obstruction is not None:
        if obstruction.HasField("fraction_obstructed"):
            fraction = _metric(obstruction.fraction_obstructed, 0, 1)
        if obstruction.HasField("currently_obstructed"):
            currently = bool(obstruction.currently_obstructed)
    values = {
        "state": state,
        "pop_ping_latency_ms": _metric(_optional(status, "pop_ping_latency_ms"), 0, 60000),
        "pop_ping_drop_rate": _metric(_optional(status, "pop_ping_drop_rate"), 0, 1),
        "downlink_throughput_bps": _metric(_optional(status, "downlink_throughput_bps"), 0, 10**12),
        "uplink_throughput_bps": _metric(_optional(status, "uplink_throughput_bps"), 0, 10**12),
        "snr": _metric(_optional(status, "snr"), -1000, 1000),
        "fraction_obstructed": fraction,
        "currently_obstructed": currently,
    }
    return values


def _optional(message, field):
    return getattr(message, field) if message.HasField(field) else None


def _metric(value, minimum, maximum):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) and minimum <= number <= maximum else None


def validate_dish_snapshot(value):
    expected = {"state", "pop_ping_latency_ms", "pop_ping_drop_rate",
        "downlink_throughput_bps", "uplink_throughput_bps", "snr",
        "fraction_obstructed", "currently_obstructed"}
    if not isinstance(value, dict) or set(value) != expected:
        raise StarlinkUnavailable("invalid_response")
    if value["state"] is not None and (not isinstance(value["state"], str) or len(value["state"]) > 32):
        raise StarlinkUnavailable("invalid_response")
    for field, (low, high) in {
        "pop_ping_latency_ms": (0, 60000), "pop_ping_drop_rate": (0, 1),
        "downlink_throughput_bps": (0, 10**12), "uplink_throughput_bps": (0, 10**12),
        "snr": (-1000, 1000), "fraction_obstructed": (0, 1),
    }.items():
        item = value[field]
        if item is not None and (type(item) not in (int, float) or not math.isfinite(item) or not low <= item <= high):
            raise StarlinkUnavailable("invalid_response")
    if value["currently_obstructed"] is not None and type(value["currently_obstructed"]) is not bool:
        raise StarlinkUnavailable("invalid_response")
    return value


class StarlinkGrpcClient:
    """Minimal client for SpaceX Device.Handle(GetDiagnostics)."""

    def get_diagnostics(self, host, port, timeout=RPC_TIMEOUT_SECONDS):
        try:
            from . import starlink_device_pb2 as messages
        except ImportError as exc:
            raise StarlinkUnavailable("dependency_missing") from exc
        response = self._call(host, port, timeout,
            messages.Request(get_diagnostics=messages.GetDiagnosticsRequest()), "wifi_get_diagnostics")
        return normalize_diagnostics(response)

    def get_dish_status(self, host, port, timeout=RPC_TIMEOUT_SECONDS):
        try:
            from . import starlink_device_pb2 as messages
        except ImportError as exc:
            raise StarlinkUnavailable("dependency_missing") from exc
        response = self._call(host, port, timeout,
            messages.Request(get_status=messages.GetStatusRequest()), "dish_get_status")
        return normalize_dish_status(response)

    def _call(self, host, port, timeout, request, expected_response):
        validate_target(host, port)
        try:
            import grpc
            from . import starlink_device_pb2 as messages
        except ImportError as exc:
            raise StarlinkUnavailable("dependency_missing") from exc

        target = f"{host}:{port}"
        channel = grpc.insecure_channel(target, options=(("grpc.enable_retries", 0),))
        deadline = time.monotonic() + timeout
        try:
            try:
                grpc.channel_ready_future(channel).result(timeout=timeout)
            except grpc.FutureTimeoutError as exc:
                raise StarlinkUnavailable("timeout") from exc
            remaining = max(0.05, deadline - time.monotonic())
            method = channel.unary_unary(
                "/SpaceX.API.Device.Device/Handle",
                request_serializer=messages.Request.SerializeToString,
                response_deserializer=messages.Response.FromString,
            )
            try:
                response = method(request, timeout=remaining)
            except grpc.RpcError as exc:
                if exc.code() == grpc.StatusCode.UNIMPLEMENTED:
                    raise StarlinkUnsupported("unsupported") from exc
                if exc.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                    raise StarlinkUnavailable("timeout") from exc
                raise StarlinkUnavailable("unavailable") from exc
            if response.WhichOneof("response") != expected_response:
                raise StarlinkUnsupported("unsupported")
            return getattr(response, expected_response)
        finally:
            channel.close()


class StarlinkStore:
    def _init_starlink(self):
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS starlink_config(
            id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL,
            host TEXT NOT NULL, port INTEGER NOT NULL, revision INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS starlink_state(
            id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS starlink_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT, received REAL NOT NULL,
            status TEXT NOT NULL, ethernet_clients INTEGER, clients_2ghz INTEGER,
            clients_5ghz INTEGER, total_clients INTEGER);
          CREATE INDEX IF NOT EXISTS starlink_history_time ON starlink_history(received,id);
          CREATE TABLE IF NOT EXISTS starlink_dish_state(
            id INTEGER PRIMARY KEY CHECK(id=1), data TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS starlink_dish_history(
            id INTEGER PRIMARY KEY AUTOINCREMENT, received REAL NOT NULL,
            status TEXT NOT NULL, state TEXT, latency_ms REAL, drop_rate REAL,
            downlink_bps REAL, uplink_bps REAL, snr REAL,
            fraction_obstructed REAL, currently_obstructed INTEGER);
          CREATE INDEX IF NOT EXISTS starlink_dish_history_time ON starlink_dish_history(received,id);
        """)
        columns = {row[1] for row in self.db.execute("PRAGMA table_info(starlink_config)")}
        if "dish_enabled" not in columns:
            self.db.execute("ALTER TABLE starlink_config ADD COLUMN dish_enabled INTEGER NOT NULL DEFAULT 0")
        if "dish_host" not in columns:
            self.db.execute(f"ALTER TABLE starlink_config ADD COLUMN dish_host TEXT NOT NULL DEFAULT '{DEFAULT_DISH_HOST}'")
        if "dish_port" not in columns:
            self.db.execute(f"ALTER TABLE starlink_config ADD COLUMN dish_port INTEGER NOT NULL DEFAULT {DEFAULT_DISH_PORT}")
        initial = {"status": "unavailable", "observed_at": None,
            "last_attempt_at": None, "last_success_at": None, "error": "not_configured",
            "router": None, "networks": []}
        dish_initial = {"status": "unavailable", "observed_at": None,
            "last_attempt_at": None, "last_success_at": None, "error": "not_configured", "metrics": None}
        with self.db:
            self.db.execute("INSERT OR IGNORE INTO starlink_config(id,enabled,host,port,revision,dish_enabled,dish_host,dish_port) VALUES(1,0,'192.168.1.1',9000,1,0,?,?)", (DEFAULT_DISH_HOST, DEFAULT_DISH_PORT))
            self.db.execute("INSERT OR IGNORE INTO starlink_state VALUES(1,?)", (json.dumps(initial),))
            self.db.execute("INSERT OR IGNORE INTO starlink_dish_state VALUES(1,?)", (json.dumps(dish_initial),))
            row = self.db.execute("SELECT data FROM starlink_state WHERE id=1").fetchone()
            saved = json.loads(row[0])
            if saved.get("status") == "available":
                saved["status"] = "stale"
                saved["error"] = "waiting_for_poll"
                self.db.execute("UPDATE starlink_state SET data=? WHERE id=1", (json.dumps(saved),))
            row = self.db.execute("SELECT data FROM starlink_dish_state WHERE id=1").fetchone()
            saved = json.loads(row[0])
            if saved.get("status") == "available":
                saved["status"] = "stale"
                saved["error"] = "waiting_for_poll"
                self.db.execute("UPDATE starlink_dish_state SET data=? WHERE id=1", (json.dumps(saved),))

    def starlink_configuration(self):
        with self.lock:
            enabled, host, port, revision, dish_enabled, dish_host, dish_port = self.db.execute(
                "SELECT enabled,host,port,revision,dish_enabled,dish_host,dish_port FROM starlink_config WHERE id=1").fetchone()
            return {"enabled": bool(enabled), "host": host, "port": port, "revision": revision,
                "dish_enabled": bool(dish_enabled), "dish_host": dish_host, "dish_port": dish_port}

    def starlink_etag(self):
        return f'"starlink-{self.starlink_configuration()["revision"]}"'

    def replace_starlink_configuration(self, body, expected):
        from .dashboard import DashboardError
        legacy = isinstance(body, dict) and set(body) == {"enabled", "host", "port"}
        if not isinstance(body, dict) or (not legacy and set(body) != {
                "enabled", "host", "port", "dish_enabled", "dish_host", "dish_port"}):
            raise DashboardError("Provide router and dish monitoring settings only.", 422, "invalid_starlink_config")
        if type(body["enabled"]) is not bool:
            raise DashboardError("Enabled must be a boolean.", 422, "invalid_starlink_config", "enabled")
        if not legacy and type(body["dish_enabled"]) is not bool:
            raise DashboardError("Dish enabled must be a boolean.", 422, "invalid_starlink_config", "dish_enabled")
        try:
            host, port = validate_target(body["host"], body["port"])
        except ValueError as exc:
            path = "host" if "private IPv4" in str(exc) else "port"
            raise DashboardError(str(exc), 422, "invalid_starlink_target", path) from exc
        if legacy:
            current = self.starlink_configuration()
            dish_enabled, dish_host, dish_port = current["dish_enabled"], current["dish_host"], current["dish_port"]
        else:
            try:
                dish_host, dish_port = validate_target(body["dish_host"], body["dish_port"])
            except ValueError as exc:
                path = "dish_host" if "private IPv4" in str(exc) else "dish_port"
                raise DashboardError(str(exc), 422, "invalid_starlink_target", path) from exc
            dish_enabled = body["dish_enabled"]
        with self.lock, self.db:
            row = self.db.execute("SELECT revision FROM starlink_config WHERE id=1").fetchone()
            if expected != f'"starlink-{row[0]}"':
                raise DashboardError("Starlink settings changed. Reload before saving.", 412, "starlink_config_conflict")
            revision = row[0] + 1
            self.db.execute("UPDATE starlink_config SET enabled=?,host=?,port=?,dish_enabled=?,dish_host=?,dish_port=?,revision=? WHERE id=1",
                (int(body["enabled"]), host, port, int(dish_enabled), dish_host, dish_port, revision))
            return {"enabled": body["enabled"], "host": host, "port": port, "revision": revision,
                "dish_enabled": dish_enabled, "dish_host": dish_host, "dish_port": dish_port}

    def starlink_document(self):
        with self.lock:
            enabled, data, dish_enabled, dish_data = self.db.execute(
                "SELECT c.enabled,s.data,c.dish_enabled,d.data FROM starlink_config c JOIN starlink_state s ON s.id=1 JOIN starlink_dish_state d ON d.id=1 WHERE c.id=1").fetchone()
            snapshot = json.loads(data)
            if not enabled:
                snapshot["status"] = "disabled"
                snapshot["error"] = None
            dish = json.loads(dish_data)
            if not dish_enabled:
                dish["status"] = "disabled"
                dish["error"] = None
            dish_rows = self.db.execute("""
                SELECT received,status,state,latency_ms,drop_rate,downlink_bps,uplink_bps,snr,
                       fraction_obstructed,currently_obstructed
                FROM starlink_dish_history WHERE received>=? ORDER BY id DESC LIMIT ?
            """, (time.time()-7*86400, HISTORY_LIMIT)).fetchall()
            dish["history"] = [dict(received_at=r[0],status=r[1],state=r[2],
                pop_ping_latency_ms=r[3],pop_ping_drop_rate=r[4],downlink_throughput_bps=r[5],
                uplink_throughput_bps=r[6],snr=r[7],fraction_obstructed=r[8],currently_obstructed=None if r[9] is None else bool(r[9]))
                for r in reversed(dish_rows)]
            snapshot["dish"] = dish
            rows = self.db.execute("""
                SELECT received,status,ethernet_clients,clients_2ghz,clients_5ghz,total_clients
                FROM starlink_history WHERE received>=? ORDER BY id DESC LIMIT ?
            """, (time.time()-7*86400, HISTORY_LIMIT)).fetchall()
            snapshot["history"] = [dict(received_at=r[0],status=r[1],ethernet_clients=r[2],
                clients_2ghz=r[3],clients_5ghz=r[4],total_clients=r[5]) for r in reversed(rows)]
            return snapshot

    def starlink_record(self, status, received, error=None, router=None, networks=None, last_success_at=None):
        router = router or None
        networks = networks or []
        with self.lock, self.db:
            previous = self.db.execute("SELECT data FROM starlink_state WHERE id=1").fetchone()
            old = json.loads(previous[0]) if previous else {}
            if status == "available":
                observed_at = received
                last_success_at = received
                visible_router, visible_networks = router, networks
            else:
                observed_at = old.get("observed_at")
                last_success_at = last_success_at or old.get("last_success_at")
                visible_router = old.get("router")
                visible_networks = old.get("networks", [])
                if status == "unavailable" and last_success_at is not None:
                    status = "stale"
            data = {"status": status, "observed_at": observed_at,
                "last_attempt_at": received, "last_success_at": last_success_at,
                "error": error, "router": visible_router, "networks": visible_networks}
            sums = []
            for key in ("clients_ethernet", "clients_2ghz", "clients_5ghz"):
                values = [n[key] for n in networks if type(n.get(key)) is int]
                sums.append(sum(values) if values else None)
            total = sum(sums) if any(v is not None for v in sums) else None
            self.db.execute("INSERT OR REPLACE INTO starlink_state VALUES(1,?)", (json.dumps(data),))
            self.db.execute("INSERT INTO starlink_history(received,status,ethernet_clients,clients_2ghz,clients_5ghz,total_clients) VALUES(?,?,?,?,?,?)",
                (received, status, *(sums if status == "available" else [None,None,None]), total if status == "available" else None))
            self.db.execute("DELETE FROM starlink_history WHERE received<?", (received-HISTORY_DAYS*86400,))
            self.db.execute("DELETE FROM starlink_history WHERE id NOT IN (SELECT id FROM starlink_history ORDER BY id DESC LIMIT ?)",
                (MAX_HISTORY_ROWS,))
        return data

    def starlink_prune(self, days):
        self.db.execute("DELETE FROM starlink_history WHERE received<?", (time.time()-days*86400,))
        self.db.execute("DELETE FROM starlink_dish_history WHERE received<?", (time.time()-days*86400,))

    def starlink_dish_record(self, status, received, error=None, metrics=None):
        metrics = validate_dish_snapshot(metrics) if metrics is not None else None
        with self.lock, self.db:
            row = self.db.execute("SELECT data FROM starlink_dish_state WHERE id=1").fetchone()
            old = json.loads(row[0]) if row else {}
            if status == "available":
                observed, success, visible = received, received, metrics
            else:
                observed, success, visible = old.get("observed_at"), old.get("last_success_at"), old.get("metrics")
                if status == "unavailable" and success is not None:
                    status = "stale"
            data = {"status":status,"observed_at":observed,"last_attempt_at":received,
                "last_success_at":success,"error":error,"metrics":visible}
            self.db.execute("INSERT OR REPLACE INTO starlink_dish_state VALUES(1,?)", (json.dumps(data),))
            values = metrics or {}
            self.db.execute("""INSERT INTO starlink_dish_history(received,status,state,latency_ms,drop_rate,
                downlink_bps,uplink_bps,snr,fraction_obstructed,currently_obstructed)
                VALUES(?,?,?,?,?,?,?,?,?,?)""", (received,status,values.get("state"),
                values.get("pop_ping_latency_ms") if status == "available" else None,
                values.get("pop_ping_drop_rate") if status == "available" else None,
                values.get("downlink_throughput_bps") if status == "available" else None,
                values.get("uplink_throughput_bps") if status == "available" else None,
                values.get("snr") if status == "available" else None,
                values.get("fraction_obstructed") if status == "available" else None,
                None if status != "available" or values.get("currently_obstructed") is None else int(values["currently_obstructed"])))
            self.db.execute("DELETE FROM starlink_dish_history WHERE received<?", (received-HISTORY_DAYS*86400,))
            self.db.execute("DELETE FROM starlink_dish_history WHERE id NOT IN (SELECT id FROM starlink_dish_history ORDER BY id DESC LIMIT ?)", (MAX_HISTORY_ROWS,))
        return data


class StarlinkPoller:
    def __init__(self, store, client=None, interval=POLL_SECONDS, timeout=RPC_TIMEOUT_SECONDS):
        self.store = store
        self.client = client or StarlinkGrpcClient()
        self.interval = interval
        self.timeout = timeout
        self.stop = threading.Event()
        self.wake_event = threading.Event()
        self.last_attempt_monotonic = None

    def wake(self):
        self.wake_event.set()

    def once(self, force=False):
        config = self.store.starlink_configuration()
        if not config["enabled"] and not config["dish_enabled"]:
            return self.store.starlink_document()
        now_mono = time.monotonic()
        if not force and self.last_attempt_monotonic is not None and now_mono-self.last_attempt_monotonic < self.interval:
            return self.store.starlink_document()
        self.last_attempt_monotonic = now_mono
        received = time.time()
        if config["enabled"]:
            try:
                result = validate_snapshot(self.client.get_diagnostics(config["host"], config["port"], self.timeout))
                self.store.starlink_record("available", received,
                    router={"hardware_version": result["hardware_version"], "software_version": result["software_version"]},
                    networks=result["networks"])
            except StarlinkUnsupported:
                self.store.starlink_record("unsupported", received, error="unsupported")
            except StarlinkUnavailable as exc:
                self.store.starlink_record("unavailable", received, error=str(exc)[:64] or "unavailable")
            except Exception:
                self.store.starlink_record("unavailable", received, error="unavailable")
        if config["dish_enabled"]:
            try:
                metrics = validate_dish_snapshot(self.client.get_dish_status(
                    config["dish_host"], config["dish_port"], self.timeout))
                self.store.starlink_dish_record("available", received, metrics=metrics)
            except StarlinkUnsupported:
                self.store.starlink_dish_record("unsupported", received, error="unsupported")
            except StarlinkUnavailable as exc:
                self.store.starlink_dish_record("unavailable", received, error=str(exc)[:64] or "unavailable")
            except Exception:
                self.store.starlink_dish_record("unavailable", received, error="unavailable")
        return self.store.starlink_document()

    def run(self):
        while not self.stop.is_set():
            config = self.store.starlink_configuration()
            if config["enabled"] or config["dish_enabled"]:
                self.once()
                wait = self.interval
            else:
                wait = 30
            self.wake_event.wait(wait)
            self.wake_event.clear()
