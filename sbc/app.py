"""Local dashboard/API server. Run: python3 -m sbc.app"""
import hmac
import json
import os
import re
import sqlite3
from pathlib import Path
import mimetypes
import threading
import uuid
from urllib.parse import urlsplit, parse_qs
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from .core import ConfigurationError, Gateway, Store, Poller, StarlinkPoller, validate_command
from .contracts import capabilities, contract
from .profiles import requested_profile
from .dashboard import DashboardError
from .sensors import profile_document,UL,device_model,sensor_endpoint
from . import plugs
from .contracts_v2 import contract_v2, capabilities_v2

STATIC = Path(__file__).parent / "static"

def make_handler(store, poller, gateway, token, starlink_poller=None):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def send(self, code, obj, headers=None):
            data = json.dumps(obj, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(data)
        def auth(self):
            return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + token)
        def read_body(self, limit=512):
            n = int(self.headers.get("Content-Length", "0"))
            if n > limit:
                raise DashboardError("Request body is too large.", 413, "body_too_large") if limit > 512 else ValueError("body size")
            if n <= 0:
                raise ValueError("body size")
            def unique(pairs):
                result = {}
                for key, value in pairs:
                    if key in result: raise ValueError("duplicate field")
                    result[key] = value
                return result
            value = json.loads(self.rfile.read(n), object_pairs_hook=unique,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite number")))
            if not isinstance(value, dict):
                raise ValueError("object required")
            return value
        def v2_error(self, status, code, message, path=""):
            return self.send(status, {"error": {"code": code, "message": message,
                "details": [{"path": path, "code": code, "message": message}] if path else []}, "request_id": str(uuid.uuid4())})
        def v2(self, method):
            if not self.auth():
                return self.v2_error(401, "unauthorized", "Dashboard token required.")
            route = urlsplit(self.path)
            try:
                requested=requested_profile(self.headers)
                profile=store.resolve_profile(requested)
                profile_route=re.fullmatch(r'/api/v2/profiles/(admin|p-[0-9a-f]{24})',route.path)
                if route.path=='/api/v2/profiles':
                    if method=='GET':return self.send(200,store.profiles_document(profile))
                    if method=='POST':return self.send(201,store.save_profile(self.read_body(4096)))
                if profile_route:
                    if method=='PUT':return self.send(200,store.save_profile(self.read_body(4096),profile_route[1]))
                    if method=='DELETE':
                        store.delete_profile(profile_route[1]);return self.send(200,{'deleted':True})
                if method == "GET":
                    if route.path == "/api/v2/system": return self.send(200, store.system_host())
                    if route.path == "/api/v2/system/database": return self.send(200, store.system_database())
                    if route.path == "/api/v2/system/purge-preview": return self.send(200, store.system_purge_preview())
                    if route.path == "/api/v2/plug-profiles":return self.send(200,plugs.profiles())
                    if route.path == "/api/v2/plugs":return self.send(200,store.plug_document())
                    if route.path == "/api/v2/sensor-profiles":return self.send(200,profile_document())
                    if route.path == "/api/v2/display":return self.send(200,store.display_document())
                    if route.path == "/api/v2/commissioning": return self.send(200, store.commissioning_document())
                    if route.path == "/api/v2/capabilities": return self.send(200, capabilities_v2())
                    if route.path == "/api/v2/openapi.json": return self.send(200, contract_v2())
                    if route.path == "/api/v2/configuration":
                        with store.lock:
                            doc = store.configuration_document(profile)
                            return self.send(200, doc, {"ETag":store.configuration_etag(profile),"X-Dashboard-Profile":profile})
                    if route.path == "/api/v2/devices": return self.send(200, store.device_views())
                    if route.path == "/api/v2/gateway": return self.send(200, dict(poller.status))
                    if route.path == "/api/v2/radio": return self.send(200, dict(poller.radio))
                    if route.path == "/api/v2/starlink": return self.send(200, store.starlink_document())
                    if route.path == "/api/v2/starlink/config":
                        return self.send(200, store.starlink_configuration(), {"ETag":store.starlink_etag()})
                    if route.path == "/api/v2/history":
                        params = parse_qs(route.query, keep_blank_values=True, strict_parsing=True)
                        if any(len(values) != 1 for values in params.values()):
                            raise DashboardError("Repeated query parameters are not allowed.", 400, "invalid_query")
                        return self.send(200, store.measurement_history({key: values[0] for key, values in params.items()}))
                if method == "POST" and route.path == "/api/v2/plugs":
                    body=self.read_body(4096)
                    if set(body)=={'job_id','action'} and body['action']=='cancel':return self.send(200,store.cancel_plug(body['job_id']))
                    if not poller.status.get('connected') or not poller.status.get('plug_extensions'):return self.v2_error(503,'gateway_upgrade_required','Connect smart-plug firmware first.')
                    return self.send(202,store.start_plug(body))
                if method == "POST" and route.path == "/api/v2/system/database/check":
                    return self.send(200, store.system_database_check())
                if method == "PUT" and route.path == "/api/v2/starlink/config":
                    expected = self.headers.get("If-Match")
                    if expected is None:
                        return self.v2_error(428, "revision_required", "Reload Starlink settings before saving.")
                    data = store.replace_starlink_configuration(self.read_body(1024), expected)
                    if starlink_poller:
                        starlink_poller.wake()
                    return self.send(200, data, {"ETag":store.starlink_etag()})
                if method == "POST" and route.path == "/api/v2/system/purge":
                    body = self.read_body(1024)
                    if set(body) != {"preview_id"} or not isinstance(body["preview_id"], str):
                        raise DashboardError("A purge preview_id is required.", 422, "invalid_preview")
                    return self.send(200, store.system_purge(body["preview_id"]))
                if method == "POST" and route.path == "/api/v2/display":
                    body=self.read_body(4096)
                    if set(body)=={'ieee','action'} and body['action']=='cancel':return self.send(200,store.cancel_display(body['ieee']))
                    if not poller.status.get('connected') or not poller.status.get('sensor_extensions'):return self.v2_error(503,'gateway_upgrade_required','Update/connect gateway firmware with sensor extensions first.')
                    return self.send(202,store.start_display(body))
                if method == "POST" and route.path == "/api/v2/commissioning":
                    body = self.read_body(4096)
                    if set(body)=={'ieee','action'} and body['action']=='cancel':
                        if not isinstance(body['ieee'],str) or not re.fullmatch('[0-9a-f]{16}',body['ieee']): raise DashboardError('Invalid IEEE address.',422)
                        return self.send(200,store.cancel_commissioning(body['ieee']))
                    if not poller.status.get('connected') or not poller.status.get('reporting_commissioning'):
                        return self.v2_error(503,'gateway_unavailable','Update/connect a gateway supporting reporting commissioning first.')
                    effective_model=body.get('model_hint')
                    if isinstance(body.get('ieee'),str) and re.fullmatch('[0-9a-f]{16}',body['ieee']):
                        with store.lock: effective_model=device_model(store._get(body['ieee']),effective_model)
                    if effective_model==UL and not poller.status.get('sensor_extensions'):return self.v2_error(503,'gateway_upgrade_required','SNZB-02UL preparation requires the new sensor extension firmware.')
                    return self.send(202,store.start_commissioning(body))
                if method == "PUT" and route.path == "/api/v2/configuration":
                    expected = self.headers.get("If-Match")
                    if expected is None: return self.v2_error(428, "revision_required", "Reload configuration before saving.")
                    if requested!=profile:raise DashboardError('Profile no longer available. Reload before saving.',409,'profile_unavailable')
                    with store.lock:
                        doc = store.replace_configuration(self.read_body(65536), expected, profile)
                        return self.send(200, doc, {"ETag":store.configuration_etag(profile),"X-Dashboard-Profile":profile})
                return self.v2_error(404, "not_found", "Resource not found.")
            except DashboardError as error:
                return self.v2_error(error.status, error.code, str(error), error.path)
            except (ValueError, UnicodeError):
                return self.v2_error(400, "malformed_request", "Invalid JSON or query parameters.")
            except sqlite3.Error:
                return self.v2_error(503, "database_unavailable", "The database health operation could not be completed.")
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
            if self.path.startswith('/api/v2/'): return self.v2("PUT")
            self.configuration("PUT")
        def do_DELETE(self):
            if self.path.startswith('/api/v2/'): return self.v2("DELETE")
            self.configuration("DELETE")
        def do_GET(self):
            path = urlsplit(self.path).path
            if path in ('/next','/next/'):
                self.send_response(302);self.send_header('Location','/')
                self.send_header('Content-Length','0');self.end_headers();return
            if path == '/' or path.startswith('/assets/'):
                relative = 'index.html' if path == '/' else path.lstrip('/')
                root = (STATIC / 'dashboard').resolve()
                candidate = (root / relative).resolve()
                if not candidate.is_relative_to(root) or not candidate.is_file():
                    return self.send(404, {'error': 'not found'})
                data = candidate.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(candidate.name)[0] or 'application/octet-stream')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-cache')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'; object-src 'none'; base-uri 'self'")
                self.send_header('X-Content-Type-Options','nosniff')
                self.end_headers();self.wfile.write(data);return
            if path in ('/app.js','/style.css') or path.startswith('/next/assets/'):
                return self.send(404, {'error':'not found'})
            if self.path.startswith('/api/v2/'): return self.v2("GET")
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
            if self.path.startswith("/api/v2/"): return self.v2("POST")
            if self.path.startswith('/api/v2/'): return self.v2("POST")
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
                if c['op']=='on_off':
                    with store.lock:
                        if plugs.identified(store._get(c['ieee'].lower())):return self.send(400,{'error':'Use acknowledged smart-plug jobs for this device.'})
                        if sensor_endpoint(store._get(c['ieee'].lower()),c['endpoint']):return self.send(400,{'error':'A sensor On/Off binding is not an appliance control.'})
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
    starlink_poller = StarlinkPoller(store)
    starlink_thread = threading.Thread(target=starlink_poller.run, daemon=True)
    thread.start()
    starlink_thread.start()
    server = ThreadingHTTPServer((os.environ.get("BIND_HOST", "127.0.0.1"), int(os.environ.get("PORT", "8080"))),
        make_handler(store, poller, gateway, token, starlink_poller))
    server.daemon_threads = True
    print(f"Dashboard listening on {server.server_address[0]}:{server.server_address[1]}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        poller.stop.set()
        starlink_poller.stop.set()
        starlink_poller.wake()
        thread.join(timeout=10)
        starlink_thread.join(timeout=10)
        server.server_close()
        store.close()
if __name__ == "__main__":
    main()
