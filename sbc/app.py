"""Local dashboard/API server. Run: python3 -m sbc.app"""
import hmac
import json
import os
import re
from pathlib import Path
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .core import ConfigurationError, Gateway, Store, Poller, validate_command
from .contracts import capabilities, contract

STATIC = Path(__file__).parent / "static"

def make_handler(store, poller, gateway, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def send(self, code, obj):
            data = json.dumps(obj, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
        def auth(self):
            return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)
        def read_body(self):
            n = int(self.headers.get("Content-Length", "0"))
            if not 0 < n <= 512:
                raise ValueError("body size")
            value = json.loads(self.rfile.read(n), parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")))
            if not isinstance(value, dict):
                raise ValueError("object required")
            return value
        def configuration(self, method):
            if not self.auth():
                return self.send(401, {"error": "token required"})
            location = re.fullmatch(r"/api/v1/locations/([a-zA-Z0-9-]+)", self.path)
            device = re.fullmatch(r"/api/v1/devices/([0-9a-fA-F]{16})/location", self.path)
            try:
                if method == "POST" and self.path == "/api/v1/locations":
                    body = self.read_body()
                    if set(body) != {"name"}:
                        raise ValueError("name required; unexpected fields")
                    return self.send(201, store.save_location(body["name"]))
                if method == "PUT" and (location or device):
                    body = self.read_body()
                    field = "name" if location else "location_id"
                    if set(body) != {field}:
                        raise ValueError(field + " required; unexpected fields")
                    result = store.save_location(body["name"], location[1]) if location else store.assign_location(device[1].lower(), body["location_id"])
                    return self.send(200, result)
                if method == "DELETE" and location:
                    store.delete_location(location[1])
                    return self.send(200, {"deleted": True})
                return self.send(404, {"error": "not found"})
            except ConfigurationError as error:
                return self.send(error.status, {"error": str(error)})
            except (ValueError, UnicodeError):
                return self.send(400, {"error": "invalid configuration"})
        def do_PUT(self):
            self.configuration("PUT")
        def do_DELETE(self):
            self.configuration("DELETE")
        def do_GET(self):
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript"), "/style.css": ("style.css", "text/css")}
            if self.path in files:
                name, mime = files[self.path]
                data = (STATIC / name).read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(data)
                return
            if not self.auth():
                return self.send(401, {"error": "token required"})
            if self.path == "/api/v1/state":
                with store.lock:
                    state = {"gateway": poller.status, "devices": store.snapshot(), "locations": store.locations()}
                self.send(200, state)
            elif self.path == "/api/v1/events":
                self.send(200, {"events": store.history()})
            elif self.path == "/api/v1/locations":
                self.send(200, {"locations": store.locations()})
            elif self.path == "/api/v1/capabilities":
                self.send(200, capabilities())
            elif self.path == "/api/v1/openapi.json":
                self.send(200, contract())
            else:
                self.send(404, {"error": "not found"})
        def do_POST(self):
            if self.path == "/api/v1/locations":
                return self.configuration("POST")
            if not self.auth():
                return self.send(401, {"error": "token required"})
            if self.path != "/api/v1/commands":
                return self.send(404, {"error": "not found"})
            try:
                c = self.read_body()
                validate_command(c)
            except (ValueError, UnicodeError):
                return self.send(400, {"error": "invalid command"})
            if not poller.status.get("connected"):
                return self.send(503, {"error": "gateway offline"})
            try:
                result = gateway.request("/api/v1/commands", c)
                self.send(202 if result.get("accepted") else 503, result)
            except Exception:
                self.send(502, {"error": "gateway command failed; not automatically retried"})
    return Handler

def main():
    token = os.environ.get("DASHBOARD_TOKEN", "")
    gt = os.environ.get("GATEWAY_TOKEN", "")
    if len(token) < 32 or len(gt) < 32:
        raise SystemExit("Set GATEWAY_TOKEN and DASHBOARD_TOKEN to independent tokens of at least 32 characters")
    db = Path(os.environ.get("DB_PATH", "data/gateway.sqlite3"))
    db.parent.mkdir(parents=True, exist_ok=True)
    store = Store(str(db))
    gateway = Gateway(os.environ.get("GATEWAY_URL", "http://127.0.0.1:8081"), gt)
    poller = Poller(gateway, store)
    thread = threading.Thread(target=poller.run, daemon=True)
    thread.start()
    server = ThreadingHTTPServer((os.environ.get("BIND_HOST", "127.0.0.1"), int(os.environ.get("PORT", "8080"))),
        make_handler(store, poller, gateway, token))
    server.daemon_threads = True
    print(f"Dashboard listening on {server.server_address[0]}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop.set()
        thread.join(timeout=10)
        server.server_close()
        store.close()
if __name__ == "__main__":
    main()
