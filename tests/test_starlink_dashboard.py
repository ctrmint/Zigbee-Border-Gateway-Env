import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from concurrent import futures
from http.server import ThreadingHTTPServer
from unittest.mock import patch

from sbc.app import make_handler
from sbc.core import Poller, Store
from sbc.starlink import (
    StarlinkPoller, StarlinkUnsupported, StarlinkUnavailable,
    StarlinkGrpcClient, validate_target, normalize_dish_status,
)

TOKEN = "starlink-test-token-" + "x" * 48


class FakeClient:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.dish_error, self.dish_response, self.calls = response, error, None, None, []

    def get_diagnostics(self, host, port, timeout):
        self.calls.append((host, port, timeout))
        if self.error:
            raise self.error
        return self.response

    def get_dish_status(self, host, port, timeout):
        self.calls.append(("dish", host, port, timeout))
        if self.dish_error:
            raise self.dish_error
        return self.dish_response


class StarlinkDashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = self.tmp.name + "/starlink.sqlite3"
        self.store = Store(self.db_path)
        self.client = FakeClient({
            "hardware_version": "v2",
            "software_version": "2026.20.0",
            "networks": [{"domain": "lan", "ipv4": "192.168.1.0/24", "ipv6": [],
                "clients_ethernet": 2, "clients_2ghz": 3, "clients_5ghz": 4}],
        })
        self.client.dish_response = {
            "state": "CONNECTED", "pop_ping_latency_ms": 33.5, "pop_ping_drop_rate": 0.01,
            "downlink_throughput_bps": 12_000_000, "uplink_throughput_bps": 1_200_000,
            "snr": None, "fraction_obstructed": 0.02, "currently_obstructed": False,
        }
        self.poller = StarlinkPoller(self.store, self.client)
        self.save_config(True)
        self.dashboard_poller = Poller(None, self.store)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
            make_handler(self.store, self.dashboard_poller, None, TOKEN, self.poller))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.store.close()
        self.tmp.cleanup()

    def save_config(self, enabled, host="192.168.1.1", port=9000, etag=None):
        etag = etag or self.store.starlink_etag()
        return self.store.replace_starlink_configuration(
            {"enabled": enabled, "host": host, "port": port}, etag)

    def request(self, path, method="GET", body=None, token=TOKEN, headers=None):
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.server.server_port, path),
            data=json.dumps(body).encode() if body is not None else None, method=method)
        if token:
            req.add_header("Authorization", "Bearer " + token)
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            return urllib.request.urlopen(req, timeout=2)
        except urllib.error.HTTPError as exc:
            return exc

    def test_target_rejects_public_dns_loopback_and_noninteger_port(self):
        for host in ("8.8.8.8", "localhost", "127.0.0.1", "::1", "192.168.1.1.example"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                validate_target(host, 9000)
        for port in (True, 0, 65536, "9000"):
            with self.subTest(port=port), self.assertRaises(ValueError):
                validate_target("192.168.1.1", port)
        self.assertEqual(validate_target("10.2.3.4", 9000), ("10.2.3.4", 9000))

    def test_disabled_poller_does_not_contact_router(self):
        self.save_config(False)
        poller = StarlinkPoller(self.store, self.client)
        self.assertEqual(poller.once()["status"], "disabled")
        self.assertEqual(self.client.calls, [])

    def test_poll_caches_diagnostics_and_records_bounded_count_history(self):
        poller = StarlinkPoller(self.store, self.client)
        result = poller.once(force=True)
        self.assertEqual(result["status"], "available")
        doc = self.store.starlink_document()
        self.assertEqual(doc["router"], {"hardware_version": "v2", "software_version": "2026.20.0"})
        self.assertEqual(doc["networks"][0]["clients_5ghz"], 4)
        self.assertEqual(doc["history"][-1]["total_clients"], 9)
        self.assertNotIn("id", json.dumps(doc))
        self.assertEqual(self.client.calls, [("192.168.1.1", 9000, 3)])

    def test_dish_performance_poll_and_history_are_independent(self):
        config = self.store.starlink_configuration()
        body = {key: config[key] for key in ("enabled", "host", "port", "dish_enabled", "dish_host", "dish_port")}
        body["dish_enabled"] = True
        self.store.replace_starlink_configuration(body, self.store.starlink_etag())
        poller = StarlinkPoller(self.store, self.client)
        result = poller.once(force=True)
        dish = result["dish"]
        self.assertEqual(dish["status"], "available")
        self.assertEqual(dish["metrics"]["state"], "CONNECTED")
        self.assertEqual(dish["metrics"]["pop_ping_latency_ms"], 33.5)
        self.assertEqual(dish["history"][-1]["downlink_throughput_bps"], 12_000_000)
        self.assertEqual(self.client.calls[-1], ("dish", "192.168.100.1", 9200, 3))
        self.assertNotIn("id", json.dumps(dish))

    def test_unavailable_dish_keeps_router_available_and_old_dish_sample_stale(self):
        config = self.store.starlink_configuration()
        body = {key: config[key] for key in ("enabled", "host", "port", "dish_enabled", "dish_host", "dish_port")}
        body["dish_enabled"] = True
        self.store.replace_starlink_configuration(body, self.store.starlink_etag())
        poller = StarlinkPoller(self.store, self.client)
        self.assertEqual(poller.once(force=True)["dish"]["status"], "available")
        replacement = FakeClient(self.client.response)
        replacement.dish_error = StarlinkUnavailable("timeout")
        poller.client = replacement
        result = poller.once(force=True)
        self.assertEqual(result["status"], "available")
        self.assertEqual(result["dish"]["status"], "stale")
        self.assertEqual(result["dish"]["error"], "timeout")

    def test_dish_optional_values_remain_missing_instead_of_becoming_zero(self):
        from sbc import starlink_device_pb2 as messages
        result = normalize_dish_status(messages.DishGetStatusResponse())
        self.assertIsNone(result["pop_ping_latency_ms"])
        self.assertIsNone(result["downlink_throughput_bps"])
        self.assertIsNone(result["fraction_obstructed"])

    def test_failed_poll_is_stale_and_does_not_falsify_old_sample(self):
        poller = StarlinkPoller(self.store, self.client)
        success = poller.once(force=True)
        stamp = success["observed_at"]
        poller.client = FakeClient(error=StarlinkUnavailable("timeout"))
        stale = poller.once(force=True)
        self.assertEqual(stale["status"], "stale")
        self.assertEqual(stale["observed_at"], stamp)
        self.assertEqual(stale["error"], "timeout")
        self.assertEqual(self.store.starlink_document()["history"][-1]["status"], "stale")

    def test_unimplemented_is_reported_unsupported(self):
        poller = StarlinkPoller(self.store, FakeClient(error=StarlinkUnsupported("unsupported")))
        self.assertEqual(poller.once(force=True)["status"], "unsupported")

    def test_configuration_survives_restart_and_old_live_state_becomes_stale(self):
        poller = StarlinkPoller(self.store, self.client)
        poller.once(force=True)
        self.store.close()
        self.store = Store(self.db_path)
        self.assertEqual(self.store.starlink_configuration()["host"], "192.168.1.1")
        self.assertEqual(self.store.starlink_configuration()["enabled"], True)
        self.assertEqual(self.store.starlink_document()["status"], "stale")

    def test_history_is_retained_and_included_in_system_purge(self):
        self.poller.once(force=True)
        self.store.starlink_dish_record("available", time.time(), metrics=self.client.dish_response)
        with self.store.lock, self.store.db:
            self.store.db.execute("UPDATE starlink_history SET received=?", (time.time()-61*86400,))
            self.store.db.execute("UPDATE starlink_dish_history SET received=?", (time.time()-61*86400,))
        self.store.prune(60)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM starlink_history").fetchone()[0], 0)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM starlink_dish_history").fetchone()[0], 0)

    def test_authenticated_api_etag_validation_and_refresh(self):
        unauthorized = self.request("/api/v2/starlink", token=None)
        self.assertEqual(unauthorized.code, 401)
        self.poller.once(force=True)
        response = self.request("/api/v2/starlink")
        self.assertEqual(response.status, 200)
        self.assertEqual(json.loads(response.read())["status"], "available")
        config = self.request("/api/v2/starlink/config")
        etag = config.headers["ETag"]
        self.assertEqual(json.loads(config.read())["port"], 9000)
        missing_revision = self.request("/api/v2/starlink/config", "PUT",
            {"enabled": True, "host": "192.168.1.3", "port": 9000})
        self.assertEqual(missing_revision.code, 428)
        conflict = self.request("/api/v2/starlink/config", "PUT",
            {"enabled": True, "host": "192.168.1.3", "port": 9000}, headers={"If-Match": '"starlink-0"'})
        self.assertEqual(conflict.code, 412)
        invalid = self.request("/api/v2/starlink/config", "PUT",
            {"enabled": True, "host": "8.8.8.8", "port": 9000}, headers={"If-Match": etag})
        self.assertEqual(invalid.code, 422)
        saved = self.request("/api/v2/starlink/config", "PUT",
            {"enabled": True, "host": "192.168.1.3", "port": 9000}, headers={"If-Match": etag})
        self.assertEqual(saved.status, 200)
        self.assertEqual(json.loads(saved.read())["host"], "192.168.1.3")

    def test_fake_grpc_device_exercises_official_handle_wire_shape(self):
        import grpc
        from sbc import starlink_device_pb2 as messages

        def handle(request, context):
            if request.WhichOneof("request") == "get_diagnostics":
                return messages.Response(wifi_get_diagnostics=messages.WifiGetDiagnosticsResponse(
                    id="must-not-be-stored", hardware_version="v3", software_version="2026.20.1",
                    networks=[messages.WifiGetDiagnosticsResponse.Network(
                        domain="lan", ipv4="192.168.1.0/24", clients_ethernet=1,
                        clients_2ghz=2, clients_5ghz=3)]))
            self.assertEqual(request.WhichOneof("request"), "get_status")
            return messages.Response(dish_get_status=messages.DishGetStatusResponse(
                state=messages.DishGetStatusResponse.CONNECTED, pop_ping_latency_ms=22.4,
                pop_ping_drop_rate=0.01, downlink_throughput_bps=8_000_000,
                uplink_throughput_bps=900_000,
                obstruction_stats=messages.DishObstructionStats(fraction_obstructed=0.02,
                    currently_obstructed=False)))

        server = grpc.server(futures.ThreadPoolExecutor(max_workers=1))
        handler = grpc.unary_unary_rpc_method_handler(handle,
            request_deserializer=messages.Request.FromString,
            response_serializer=messages.Response.SerializeToString)
        server.add_generic_rpc_handlers((grpc.method_handlers_generic_handler(
            "SpaceX.API.Device.Device", {"Handle": handler}),))
        port = server.add_insecure_port("127.0.0.1:0")
        server.start()
        self.addCleanup(server.stop, 0)
        with patch("sbc.starlink.validate_target", return_value=("127.0.0.1", port)):
            result = StarlinkGrpcClient().get_diagnostics("127.0.0.1", port, timeout=2)
        self.assertEqual(result["hardware_version"], "v3")
        self.assertEqual(result["networks"][0]["clients_2ghz"], 2)
        self.assertNotIn("must-not-be-stored", json.dumps(result))
        with patch("sbc.starlink.validate_target", return_value=("127.0.0.1", port)):
            dish = StarlinkGrpcClient().get_dish_status("127.0.0.1", port, timeout=2)
        self.assertEqual(dish["state"], "CONNECTED")
        self.assertEqual(dish["downlink_throughput_bps"], 8_000_000)


if __name__ == "__main__":
    unittest.main()
