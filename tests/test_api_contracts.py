"""Validate real HTTP payloads against the published API schemas."""
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error

from jsonschema import Draft202012Validator

from sbc.app import make_handler
from sbc.contracts import contract
from sbc.core import Gateway, Poller, Store
from sbc.simulator import Simulation, make_handler as simulator_handler
from http.server import ThreadingHTTPServer

TOKEN = "c" * 64


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name + "/contract.sqlite3")
        self.servers = []
        self.sim = Simulation()
        self.gateway = self.serve(simulator_handler(self.sim, TOKEN))
        self.poller = Poller(self.gateway, self.store)
        self.dashboard = self.serve(make_handler(self.store, self.poller, self.gateway, TOKEN))

    def serve(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.servers.append((server, thread))
        return Gateway(f"http://127.0.0.1:{server.server_port}", TOKEN)

    def tearDown(self):
        for server, thread in reversed(self.servers):
            server.shutdown()
            server.server_close()
            thread.join()
        self.store.close()
        self.tmp.cleanup()

    def validate(self, service, name, payload):
        document = contract(service)
        schema = dict(document["components"]["schemas"][name], components=document["components"])
        Draft202012Validator(schema).validate(payload)

    def test_live_responses(self):
        self.validate("dashboard", "State", self.dashboard.request("/api/v1/state"))
        self.poller.once()
        for path, name in (("health", "Health"), ("devices", "Registry"), ("events?after=0", "EventBatch")):
            self.validate("gateway", name, self.gateway.request("/api/v1/" + path))
        for path, name in (("state", "State"), ("events", "History"), ("capabilities", "Capabilities")):
            self.validate("dashboard", name, self.dashboard.request("/api/v1/" + path))
        command = {"op": "permit_join", "seconds": 0}
        self.validate("dashboard", "Command", command)
        self.validate("dashboard", "CommandResult", self.dashboard.request("/api/v1/commands", command))
        self.assertEqual(self.dashboard.request("/api/v1/openapi.json"), contract())

    def test_authenticated_contract_discovery(self):
        unauthorized = Gateway(self.dashboard.url, "wrong")
        for path in ("capabilities", "openapi.json"):
            with self.assertRaises(urllib.error.HTTPError) as error:
                unauthorized.request("/api/v1/" + path)
            self.assertEqual(error.exception.code, 401)
            self.validate("dashboard", "Error", json.load(error.exception))
        features = self.dashboard.request("/api/v1/capabilities")["features"]
        self.assertTrue(features.pop('locations'))
        for feature in ('device_configuration', 'dashboard_layouts', 'history_query'):
            self.assertTrue(features.pop(feature))
        self.assertFalse(any(features.values()))

    def test_error_responses(self):
        for command, status in (({"op": []}, 400), ({"op": "permit_join", "seconds": 60}, 503)):
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.dashboard.request("/api/v1/commands", command)
            self.assertEqual(error.exception.code, status)
            self.validate("dashboard", "Error", json.load(error.exception))

    def test_exported_contracts_and_schema_validity(self):
        root = Path(__file__).resolve().parents[1] / "docs" / "api"
        for service in ("dashboard", "gateway"):
            document = contract(service)
            self.assertEqual(json.loads((root / f"{service}-v1.openapi.json").read_text()), document)
            for schema in document["components"]["schemas"].values():
                Draft202012Validator.check_schema(schema)


if __name__ == "__main__":
    unittest.main()
