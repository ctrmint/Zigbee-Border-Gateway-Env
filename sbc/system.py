"""Bounded host and SQLite health summaries for the authenticated dashboard."""
import os
import platform
import secrets
import shutil
import socket
import time
from pathlib import Path

RETENTION_DAYS = 60
PURGE_TABLES = {
    "events": ("received",),
    "measurements": ("received",),
    "signal_samples": ("received",),
    "ingestion_gaps": ("end",),
    "plug_discontinuities": ("received",),
}


def _read(path):
    try:
        return Path(path).read_text(errors="replace").strip()
    except (OSError, ValueError):
        return None


def _meminfo():
    values = {}
    for line in (_read("/proc/meminfo") or "").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            values[parts[0].rstrip(":")] = int(parts[1]) * 1024
    return values


def _os_release():
    result = {}
    for line in (_read("/etc/os-release") or "").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            result[key] = value.strip().strip('"')
    return result


class SystemStore:
    def _init_system(self, db_path):
        self.system_db_path = Path(db_path).resolve()
        self.system_started = time.monotonic()
        self.system_lock = __import__("threading").RLock()
        self.system_host_cache = None
        self.system_host_cache_at = 0
        self.system_cpu_previous = None
        self.system_check = {"status": "not_checked", "checked_at": None}
        self.system_purges = {}

    def system_host(self):
        now = time.monotonic()
        with self.system_lock:
            if self.system_host_cache and now - self.system_host_cache_at < 15:
                return self.system_host_cache
            release = _os_release()
            model = _read("/proc/device-tree/model")
            model = model.replace("\x00", "").strip() if model else None
            try:
                uptime = float((_read("/proc/uptime") or "").split()[0])
            except (ValueError, IndexError):
                uptime = None
            try:
                load = list(os.getloadavg())
            except (OSError, AttributeError):
                load = None
            cpu_line = next((line for line in (_read("/proc/stat") or "").splitlines() if line.startswith("cpu ")), None)
            cpu_pct = None
            if cpu_line:
                vals = [int(v) for v in cpu_line.split()[1:]]
                total, idle = sum(vals), vals[3] + (vals[4] if len(vals) > 4 else 0)
                if self.system_cpu_previous:
                    old_total, old_idle = self.system_cpu_previous
                    delta = total - old_total
                    if delta > 0:
                        cpu_pct = round(100 * (delta - idle + old_idle) / delta, 1)
                self.system_cpu_previous = (total, idle)
            mem = _meminfo()
            mem_total = mem.get("MemTotal")
            mem_available = mem.get("MemAvailable")
            swap_total, swap_free = mem.get("SwapTotal"), mem.get("SwapFree")
            try:
                disk = shutil.disk_usage("/")
                disk_data = {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free,
                             "used_percent": round(100 * disk.used / disk.total, 1) if disk.total else None}
            except OSError:
                disk_data = None
            try:
                thermal = int((_read("/sys/class/thermal/thermal_zone0/temp") or "")) / 1000
            except (ValueError, TypeError):
                thermal = None
            interfaces = []
            ipv6_by_iface = {}
            for line in (_read("/proc/net/if_inet6") or "").splitlines():
                parts = line.split()
                if len(parts) == 6:
                    try: ipv6_by_iface.setdefault(parts[5], []).append(socket.inet_ntop(socket.AF_INET6, bytes.fromhex(parts[0])))
                    except (ValueError, OSError): pass
            for iface in sorted(Path("/sys/class/net").glob("*")):
                name = iface.name
                state = _read(iface / "operstate")
                addresses = []
                try:
                    import fcntl
                    import struct
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    try:
                        raw = fcntl.ioctl(sock.fileno(), 0x8915, struct.pack("256s", name[:15].encode()))[20:24]
                        addresses.append(socket.inet_ntoa(raw))
                    finally:
                        sock.close()
                except (OSError, ImportError):
                    pass
                interfaces.append({"name": name, "state": state, "ipv4": addresses, "ipv6": ipv6_by_iface.get(name, [])})
            sync = None
            timedate = _read("/run/systemd/timesync/synchronized")
            if timedate is not None:
                sync = True
            data = {
                "collected_at": time.time(),
                "host": {"model": model, "os": release.get("PRETTY_NAME"), "kernel": platform.release(),
                         "architecture": platform.machine(), "uptime_seconds": round(uptime) if uptime is not None else None,
                         "time_synchronized": sync, "process": {"state": "running", "pid": os.getpid(),
                         "uptime_seconds": round(now - self.system_started), "restart_count": None,
                         "manager": "not_available"}},
                "cpu": {"load_1_5_15": load, "utilization_percent": cpu_pct, "temperature_celsius": thermal},
                "memory": {"total_bytes": mem_total, "available_bytes": mem_available,
                           "used_percent": round(100 * (mem_total-mem_available) / mem_total, 1) if mem_total and mem_available is not None else None,
                           "swap_total_bytes": swap_total, "swap_free_bytes": swap_free},
                "disk": disk_data, "interfaces": interfaces,
            }
            warnings = []
            if data["disk"] and data["disk"]["used_percent"] is not None and data["disk"]["used_percent"] >= 90: warnings.append("Root filesystem usage is at least 90%.")
            if data["memory"]["used_percent"] is not None and data["memory"]["used_percent"] >= 90: warnings.append("Memory usage is at least 90%.")
            if thermal is not None and thermal >= 80: warnings.append("CPU temperature is at least 80 °C.")
            data["warnings"] = warnings
            self.system_host_cache, self.system_host_cache_at = data, now
            return data

    def system_database(self):
        with self.lock:
            sizes = {}
            for suffix, key in (("", "file_size_bytes"), ("-wal", "wal_size_bytes"), ("-journal", "journal_size_bytes")):
                try: sizes[key] = Path(str(self.system_db_path) + suffix).stat().st_size
                except OSError: sizes[key] = 0
            page_size = self.db.execute("PRAGMA page_size").fetchone()[0]
            page_count = self.db.execute("PRAGMA page_count").fetchone()[0]
            free_pages = self.db.execute("PRAGMA freelist_count").fetchone()[0]
            tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            names = {"devices": "devices", "locations": "locations", "profiles": "user_profiles", "events": "events",
                     "measurements": "measurements", "signal_samples": "signal_samples", "ingestion_gaps": "ingestion_gaps",
                     "plug_discontinuities": "plug_discontinuities", "commissioning_jobs": "commissioning_jobs",
                     "display_jobs": "display_jobs", "plug_jobs": "plug_jobs"}
            counts = {label: (self.db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0] if table in tables else 0)
                      for label, table in names.items()}
            oldest_newest = {}
            for table, (column,) in PURGE_TABLES.items():
                if table in tables:
                    oldest_newest[table] = {"oldest": self.db.execute(f'SELECT MIN("{column}") FROM "{table}"').fetchone()[0],
                                             "newest": self.db.execute(f'SELECT MAX("{column}") FROM "{table}"').fetchone()[0]}
            latest = self.db.execute("SELECT received FROM ingestion_state WHERE id=1").fetchone() if "ingestion_state" in tables else None
            return {"collected_at": time.time(), **sizes, "page_size": page_size, "page_count": page_count,
                    "free_pages": free_pages, "journal_mode": self.db.execute("PRAGMA journal_mode").fetchone()[0],
                    "counts": counts, "retained_range": oldest_newest, "latest_ingestion_at": latest[0] if latest else None,
                    "integrity": dict(self.system_check)}

    def system_database_check(self):
        with self.lock:
            rows = self.db.execute("PRAGMA quick_check(1)").fetchmany(2)
            result = "ok" if len(rows) == 1 and rows[0][0] == "ok" else "error"
            self.system_check = {"status": result, "checked_at": time.time(), "summary": "ok" if result == "ok" else "Database reported an integrity issue."}
            return dict(self.system_check)

    def system_purge_preview(self):
        now = time.time()
        cutoff = now - RETENTION_DAYS * 86400
        with self.lock:
            tables = {row[0] for row in self.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            counts = {}
            for table, (column,) in PURGE_TABLES.items():
                counts[table] = self.db.execute(f'SELECT COUNT(*) FROM "{table}" WHERE "{column}" < ?', (cutoff,)).fetchone()[0] if table in tables else 0
            token = secrets.token_urlsafe(24)
            self.system_purges = {key: value for key, value in self.system_purges.items() if value["expires_at"] > now}
            self.system_purges[token] = {"cutoff": cutoff, "expires_at": now + 300, "counts": counts}
            return {"preview_id": token, "cutoff": cutoff, "retention_days": RETENTION_DAYS, "expires_in_seconds": 300, "counts": counts, "total_rows": sum(counts.values())}

    def system_purge(self, preview_id):
        preview = self.system_purges.get(preview_id)
        if not preview or preview["expires_at"] <= time.time():
            self.system_purges.pop(preview_id, None)
            from .dashboard import DashboardError
            raise DashboardError("Purge preview expired; create a new preview.", 409, "preview_expired")
        with self.lock, self.db:
            cutoff = preview["cutoff"]
            deleted = {table: self.db.execute(f'DELETE FROM "{table}" WHERE "{column}" < ?', (cutoff,)).rowcount
                       for table, (column,) in PURGE_TABLES.items()
                       if self.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()}
        self.system_purges.pop(preview_id, None)
        return {"purged_at": time.time(), "cutoff": cutoff, "retention_days": RETENTION_DAYS, "deleted": deleted, "total_rows": sum(deleted.values())}
