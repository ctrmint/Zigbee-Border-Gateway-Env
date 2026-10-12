import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from jsonschema import Draft202012Validator

from sbc.app import make_handler
from sbc.contracts import contract
from sbc.core import ConfigurationError, Poller, Store
from sbc.simulator import Simulation

TOKEN = 'l' * 64


class NoGateway:
    def request(self, *args):
        raise AssertionError('Location configuration must not contact the ESP32')


class LocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + '/locations.sqlite3'
        self.store = Store(self.path)
        self.sim = Simulation()
        self.store.ingest(self.sim.boot, self.sim.events, self.sim.seq, self.sim.devices)
        self.gateway = NoGateway()
        self.poller = Poller(self.gateway, self.store)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, self.poller, self.gateway, TOKEN))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}/api/v1/'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.store.close(); self.tmp.cleanup()

    def request(self, path, body=None, method='GET', token=TOKEN, status=200, schema=None):
        request = urllib.request.Request(self.url + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.assertEqual(response.status, status)
            result = json.load(response)
        if schema:
            document = contract()
            definition = dict(document['components']['schemas'][schema], components=document['components'])
            Draft202012Validator(definition).validate(result)
        return result

    def test_multiple_devices_rename_move_and_delete(self):
        first = self.request('locations', {'name': ' Kitchen '}, 'POST', status=201, schema='Location')
        second = self.request('locations', {'name': 'Garden'}, 'POST', status=201)
        for d in self.sim.devices:
            self.request(f'devices/{d["ieee"]}/location', {'location_id': first['id']}, 'PUT', schema='LocationAssignmentResult')
        renamed = self.request('locations/' + first['id'], {'name': 'Downstairs'}, 'PUT', schema='Location')
        self.assertEqual(renamed['id'], first['id']); self.assertEqual(renamed['device_count'], 2)
        self.request('locations/' + first['id'], method='DELETE', status=409, schema='Error')
        state = self.request('state', schema='State')
        self.assertEqual([d['location_name'] for d in state['devices']], ['Downstairs', 'Downstairs'])
        self.request(f'devices/{self.sim.devices[0]["ieee"]}/location', {'location_id': second['id']}, 'PUT')
        self.request(f'devices/{self.sim.devices[1]["ieee"]}/location', {'location_id': None}, 'PUT')
        self.request('locations/' + first['id'], method='DELETE', schema='Deleted')
        locations = self.request('locations', schema='LocationList')['locations']
        self.assertEqual(locations, [dict(second, device_count=1)])

    def test_configuration_survives_poll_and_restart(self):
        location = self.store.save_location('Greenhouse')
        ieee = self.sim.devices[1]['ieee']
        self.store.assign_location(ieee, location['id'])
        self.sim.devices[1].update(nwk=0x4567, active=False)
        self.sim.measure()
        self.store.ingest(self.sim.boot, self.sim.events, self.sim.seq, self.sim.devices)
        cursor = self.store.cursor()
        self.store.close(); self.store = Store(self.path)
        device = self.store.snapshot()[1]
        self.assertEqual(device['location_name'], 'Greenhouse')
        self.assertEqual(device['location_id'], location['id'])
        self.assertEqual(device['nwk'], 0x4567); self.assertFalse(device['active'])
        self.assertEqual(self.store.cursor(), cursor)
        self.assertIn('1:1026:0', device['attributes'])

    def test_names_limits_and_validation_are_atomic(self):
        first = self.store.save_location('Straße')
        with self.assertRaises(ConfigurationError): self.store.save_location('STRASSE')
        second = self.store.save_location('Outside')
        with self.assertRaises(ConfigurationError): self.store.save_location('straße', second['id'])
        self.assertEqual(self.store.locations()[0]['name'], 'Outside')
        for name in ('', '   ', 'x' * 81, 'Kitchen\nUpstairs', '\x00', 12, None):
            with self.assertRaises(ConfigurationError): self.store.save_location(name)
        for index in range(48): self.store.save_location(f'Location {index}')
        with self.assertRaises(ConfigurationError): self.store.save_location('Overflow')
        self.assertEqual(len(self.store.locations()), 50)
        self.assertEqual(self.store.save_location('Indoor', first['id'])['id'], first['id'])

    def test_authentication_and_unknown_resources(self):
        ieee = self.sim.devices[0]['ieee']
        for path, body, method in (
            ('locations', None, 'GET'), ('locations', {'name': 'Private'}, 'POST'),
            ('locations/missing', {'name': 'Private'}, 'PUT'), ('locations/missing', None, 'DELETE'),
            (f'devices/{ieee}/location', {'location_id': None}, 'PUT')):
            self.request(path, body, method, token='wrong', status=401, schema='Error')
        self.request('locations/missing', {'name': 'Kitchen'}, 'PUT', status=404)
        self.request('locations/missing', method='DELETE', status=404)
        self.request('devices/0000000000000000/location', {'location_id': None}, 'PUT', status=404)
        self.request(f'devices/{ieee}/location', {'location_id': 'missing'}, 'PUT', status=404)
        for body in ({'location_id': []}, {'location_id': None, 'extra': True}, {}):
            self.request(f'devices/{ieee}/location', body, 'PUT', status=400)
        for body in ({'name': []}, {'name': 'Room', 'extra': True}, {}, []):
            self.request('locations', body, 'POST', status=400)
        self.assertEqual(self.store.locations(), [])
        self.assertIsNone(self.store.snapshot()[0]['location_id'])

    def test_existing_database_is_upgraded_without_losing_data(self):
        path = self.tmp.name + '/legacy.sqlite3'
        db = sqlite3.connect(path)
        try:
            with db:
                db.executescript('CREATE TABLE devices(ieee TEXT PRIMARY KEY,data TEXT NOT NULL);'
                                 'CREATE TABLE cursor(id INTEGER PRIMARY KEY CHECK(id=1),boot TEXT,seq INTEGER);')
                db.execute('INSERT INTO devices VALUES(?,?)', (self.sim.devices[0]['ieee'], json.dumps(self.store.snapshot()[0])))
                db.execute('INSERT INTO cursor VALUES(1,?,?)', ('old-boot', 42))
        finally:
            db.close()
        upgraded = Store(path)
        try:
            self.assertEqual(upgraded.cursor(), ('old-boot', 42))
            self.assertEqual(len(upgraded.snapshot()), 1)
            location = upgraded.save_location('Workshop')
            upgraded.assign_location(self.sim.devices[0]['ieee'], location['id'])
            upgraded.sync_devices(self.sim.devices)
            self.assertEqual(upgraded.snapshot()[0]['location_name'], 'Workshop')
        finally:
            upgraded.close()


if __name__ == '__main__':
    unittest.main()
