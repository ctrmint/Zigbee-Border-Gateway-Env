"""Synthetic SNZB-02P workflow coverage; fixtures are not hardware evidence."""
import time
import urllib.parse
import unittest
from jsonschema import Draft202012Validator
import test_api_contracts as contracts
from sbc.core import Store, normalize
from sbc.dashboard import source_supported
from sbc.sensors import P, profile_document
from sbc.contracts_v2 import contract_v2

IEEE = "00124b0000000057"


def policy(**changes):
    result = {"ieee": IEEE, "endpoint": 1, "min_interval": 5, "max_interval": 3600,
        "temperature_change": .2, "humidity_change": 1, "model_hint": P}
    result.update(changes)
    return result


class SNZB02PTests(contracts.ContractTests):
    test_live_responses = None
    test_authenticated_contract_discovery = None
    test_error_responses = None
    test_exported_contracts_and_schema_validity = None

    def setUp(self):
        super().setUp()
        self.device = self.sim.add_snzb02p(voltage=False)
        self.poller.once()

    def drain(self, count=18):
        for _ in range(count):
            self.poller.once()

    def job(self):
        return next(job for job in self.store.commissioning_document()["jobs"] if job["ieee"] == IEEE)

    def test_identity_profile_and_capability_driven_readings(self):
        profile_response = self.dashboard.request("/api/v2/sensor-profiles")
        schema = dict(contract_v2()["components"]["schemas"]["SensorProfiles"], components=contract_v2()["components"])
        Draft202012Validator(schema).validate(profile_response)
        profile = next(item for item in profile_response["profiles"] if item["model"] == P)
        self.assertEqual(profile["hardware_status"], "not_tested")
        self.assertEqual(profile["defaults"], {"min_interval": 5, "max_interval": 3600,
            "temperature_change": .2, "humidity_change": 1})
        view = next(item for item in self.store.device_views()["devices"] if item["ieee"] == IEEE)
        self.assertEqual(view["profile"], P)
        self.assertEqual(view["name"], "SNZB-02P")
        values = {(item["cluster"], item["attribute"]): item for item in view["measurements"]}
        self.assertEqual(values[(1026, 0)]["value"], 21.5)
        self.assertEqual(values[(1029, 0)]["value"], 48.2)
        self.assertEqual(values[(1, 33)]["value"], 95)
        self.assertNotIn((1, 32), values)
        self.assertTrue(source_supported(self.store._get(IEEE), 1, 1026, 0))
        self.assertTrue(source_supported(self.store._get(IEEE), 1, 1029, 0))
        self.assertFalse(source_supported(self.store._get(IEEE), 1, 6, 0))
        location = self.store.save_location("Utility room")
        document = self.store.configuration_document()
        document["devices"][IEEE]["location_id"] = location["id"]
        document["dashboard"]["widgets"] = [
            {"id": "snzb02p-temperature", "type": "chart", "title": "Temperature history",
             "position": 0, "time_range": 86400,
             "source": {"ieee": IEEE, "endpoint": 1, "cluster": 1026, "attribute": 0}},
            {"id": "snzb02p-humidity", "type": "numeric", "title": "Humidity",
             "position": 1, "time_range": 86400,
             "source": {"ieee": IEEE, "endpoint": 1, "cluster": 1029, "attribute": 0}},
        ]
        saved = self.store.replace_configuration(
            {key: document[key] for key in ("locations", "devices", "dashboard")},
            self.store.configuration_etag())
        self.assertEqual([widget["id"] for widget in saved["dashboard"]["widgets"]],
                         ["snzb02p-temperature", "snzb02p-humidity"])
        devices = self.dashboard.request("/api/v2/devices")
        Draft202012Validator(dict(contract_v2()["components"]["schemas"]["Devices"], components=contract_v2()["components"])).validate(devices)
        self.assertEqual(next(item for item in devices["devices"] if item["ieee"] == IEEE)["profile"], P)

    def test_reporting_setup_discovers_battery_and_preserves_history(self):
        queued = self.dashboard.request("/api/v2/commissioning", policy())
        self.assertEqual(queued["model_profile"], P)
        self.assertTrue(any(step.get("optional") and step["op"] == "bind" and step["cluster"] == 1 for step in queued["steps"]))
        self.drain()
        job = self.job()
        self.assertEqual(job["state"], "verified")
        self.assertEqual(job["identity"]["manufacturer"], "SONOFF")
        self.assertEqual(job["identity"]["model"], "SNZB-02P")
        self.assertIn(1, [step["cluster"] for step in job["steps"] if step["op"] == "bind"])
        schema = dict(contract_v2()["components"]["schemas"]["CommissioningJob"], components=contract_v2()["components"])
        Draft202012Validator(schema).validate(job)
        measurements = {(item["cluster"], item["attribute"]): item for item in
            next(item for item in self.store.device_views()["devices"] if item["ieee"] == IEEE)["measurements"]}
        self.assertEqual(measurements[(1026, 0)]["origin"], "report")
        self.assertEqual(measurements[(1029, 0)]["origin"], "report")
        self.assertEqual(measurements[(1, 33)]["value"], 95)
        query = urllib.parse.urlencode({"ieee": IEEE, "endpoint": 1, "cluster": 1026, "attribute": 0,
            "from": time.time() - 3600, "to": time.time() + 1})
        history = self.dashboard.request("/api/v2/history?" + query)
        self.assertEqual(history["items"][-1]["value"], 21.5)

    def test_normalization_rejects_invalid_sentinels_and_missing_values(self):
        self.assertEqual(normalize(1026, 0, 0x29, -32768), (None, None))
        self.assertEqual(normalize(1029, 0, 0x21, 10001), (None, None))
        self.assertEqual(normalize(1, 33, 0x20, 255), (None, None))
        self.assertEqual(normalize(1, 32, 0x20, 255), (None, None))
        self.assertEqual(normalize(1026, 0, 0x29, 2150), (21.5, "°C"))
        self.assertEqual(normalize(1029, 0, 0x21, 4820), (48.2, "%"))

    def test_user_hint_does_not_override_observed_basic_identity(self):
        self.assertEqual(self.store.start_commissioning(policy(model_hint="SONOFF SNZB-02WD"))["model_profile"], P)


if __name__ == "__main__":
    unittest.main()
