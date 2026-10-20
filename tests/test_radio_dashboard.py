import tempfile
import json
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer

from jsonschema import Draft202012Validator

from sbc.contracts import contract
from sbc.contracts_v2 import contract_v2
from sbc.core import Poller, Store
from sbc.app import make_handler
from sbc.simulator import Simulation, make_handler as simulator_handler

TOKEN = "r" * 64


class RadioGateway:
    def __init__(self, result=None, error=None):
        self.result, self.error = result, error

    def request(self, path):
        if path != "/api/v1/radio":
            raise AssertionError(f"unexpected gateway request: {path}")
        if self.error:
            raise self.error
        return self.result


class RadioDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Store(self.tmp.name + "/radio.sqlite3")
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.store.close)

    def test_radio_snapshot_cache_and_contracts(self):
        gateway = RadioGateway({
            "boot_id": "0123456789abcdef", "mode": "simulator", "ready": True,
            "uptime_ms": 10000, "channel": 20, "pan_id": 6754,
            "scope": "simulated_coordinator_local_tables",
            "neighbor_source": "synthetic_fixture_not_radio_observation",
            "route_source": "synthetic_fixture_not_radio_observation",
            "neighbors": [{"ieee": "00124b0000000001", "nwk": 4660, "device_type": 2,
                "depth": 1, "rx_on_when_idle": False, "relationship": 1, "lqi": 180,
                "rssi_dbm": -48, "outgoing_cost": 2, "age_periods": 0,
                "device_timeout_seconds": 0, "timeout_ms": 0}],
            "routes": [], "route_records": [],
        })
        poller = Poller(gateway, self.store)
        poller._refresh_radio()
        self.assertEqual(poller.radio["status"], "available")
        self.assertEqual(poller.radio["source"], "simulated_coordinator_local_tables")
        self.assertEqual(len(poller.radio["neighbors"]), 1)
        Draft202012Validator(contract_v2()["components"]["schemas"]["RadioSnapshot"]).validate(poller.radio)
        board = contract("gateway")
        self.assertIn("/api/v1/radio", board["paths"])
        hardware_sample = dict(gateway.result, scope="coordinator_local_tables",
            neighbor_source="coordinator_neighbor_table_direct_links",
            route_source="coordinator_routing_and_source_route_tables",
            dropped_events=0, latest_seq=0)
        hardware_sample.pop("mode", None)
        Draft202012Validator({"$ref": "#/components/schemas/RadioSnapshot", "components": board["components"]}).validate(hardware_sample)

    def test_unsupported_and_stale_gateway_are_distinguished(self):
        missing = urllib.error.HTTPError("http://gateway/api/v1/radio", 404, "missing", {}, None)
        gateway = RadioGateway(error=missing)
        poller = Poller(gateway, self.store)
        poller._refresh_radio()
        self.assertEqual(poller.radio["status"], "unsupported")
        self.assertIn("does not expose", poller.radio["error"])

        gateway.result = {"boot_id": "0123456789abcdef", "scope": "coordinator_local_tables",
            "ready": True, "uptime_ms": 1, "channel": 20, "pan_id": 1,
            "dropped_events": 0, "latest_seq": 1, "neighbor_source": "local", "route_source": "local",
            "neighbors": [], "routes": [], "route_records": []}
        gateway.error = None
        poller._radio_polled_at = 0
        poller._refresh_radio()
        self.assertEqual(poller.radio["status"], "available")
        gateway.error = TimeoutError("offline")
        poller._radio_polled_at = 0
        poller._refresh_radio()
        self.assertEqual(poller.radio["status"], "stale")
        self.assertEqual(len(poller.radio["neighbors"]), 0)

    def test_authenticated_dashboard_route_and_passive_simulator_endpoint(self):
        sim = Simulation()
        sequence = sim.seq
        sim_server = ThreadingHTTPServer(("127.0.0.1", 0), simulator_handler(sim, TOKEN))
        sim_thread = threading.Thread(target=sim_server.serve_forever, daemon=True)
        sim_thread.start()
        self.addCleanup(sim_thread.join)
        self.addCleanup(sim_server.server_close)
        self.addCleanup(sim_server.shutdown)
        req = urllib.request.Request(f"http://127.0.0.1:{sim_server.server_port}/api/v1/radio",
            headers={"Authorization": "Bearer " + TOKEN})
        with urllib.request.urlopen(req) as response:
            upstream = json.load(response)
        self.assertEqual(upstream["neighbor_source"], "synthetic_fixture_not_radio_observation")
        self.assertEqual(sim.seq, sequence)

        poller = Poller(None, self.store)
        poller.radio = {"status": "available", "source": "synthetic",
            "neighbors": upstream["neighbors"], "routes": [], "route_records": []}
        api_server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.store, poller, None, TOKEN))
        api_thread = threading.Thread(target=api_server.serve_forever, daemon=True)
        api_thread.start()
        self.addCleanup(api_thread.join)
        self.addCleanup(api_server.server_close)
        self.addCleanup(api_server.shutdown)
        base = f"http://127.0.0.1:{api_server.server_port}/api/v2/radio"
        with self.assertRaises(urllib.error.HTTPError) as error:
            urllib.request.urlopen(base)
        self.assertEqual(error.exception.code, 401)
        req = urllib.request.Request(base, headers={"Authorization": "Bearer " + TOKEN})
        with urllib.request.urlopen(req) as response:
            view = json.load(response)
        self.assertEqual(view["source"], "synthetic")
        Draft202012Validator(contract_v2()["components"]["schemas"]["RadioSnapshot"]).validate(view)


if __name__ == "__main__":
    unittest.main()
