import copy
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from jsonschema import Draft202012Validator

from sbc.app import make_handler
from sbc.core import Store, Poller
from sbc.dashboard import DashboardError
from sbc.contracts_v2 import contract_v2
from sbc.simulator import Simulation

TOKEN = 'v' * 64


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = self.tmp.name + '/dashboard.sqlite3'
        self.store = Store(self.path)
        self.sim = Simulation()
        self.store.ingest(self.sim.boot, self.sim.events, self.sim.seq, self.sim.devices)
        self.location = self.store.save_location('Kitchen')
        self.other = self.store.save_location('Garden')
        for d in self.sim.devices: self.store.assign_location(d['ieee'], self.location['id'])
        self.poller = Poller(None, self.store)
        self.poller.status = dict(connected=True, ready=True, error=None, gap=False, mode='simulator')
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(self.store, self.poller, None, TOKEN))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.store.close(); self.tmp.cleanup()

    def request(self, path, body=None, method='GET', tag=None, status=200, token=TOKEN, schema=None):
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
        if tag is not None: headers['If-Match']=tag
        r=urllib.request.Request(self.base+path, data=json.dumps(body).encode() if body is not None else None,
            headers=headers,method=method)
        try: response=urllib.request.urlopen(r,timeout=5)
        except urllib.error.HTTPError as e: response=e
        with response:
            self.assertEqual(response.status,status)
            data=json.load(response);etag=response.headers.get('ETag')
        if schema:
            document=contract_v2()
            Draft202012Validator({'$ref':'#/components/schemas/'+schema,'components':document['components']}).validate(data)
        return data,etag

    def draft(self):
        doc,tag=self.request('/api/v2/configuration',schema='Configuration')
        return {k:doc[k] for k in ('locations','devices','dashboard')},tag

    def restart(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.store.close()
        self.store=Store(self.path)
        self.poller.store=self.store
        self.server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,self.poller,None,TOKEN))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'

    def widget(self, kind='numeric', endpoint=1, position=0):
        return dict(id='temperature-'+str(endpoint),type=kind,title='Temperature',position=position,time_range=86400,
            source=dict(ieee=self.sim.devices[1]['ieee'],endpoint=endpoint,cluster=1026,attribute=0))

    def query(self, **changes):
        values=dict(ieee=self.sim.devices[1]['ieee'],endpoint=1,cluster=1026,attribute=0,
            **{'from':time.time()-3600,'to':time.time()+3600,'limit':2})
        values.update(changes)
        return '/api/v2/history?'+urllib.parse.urlencode(values)

    def test_config_persistence_revision_and_v1_interoperation(self):
        draft,tag=self.draft();draft['dashboard']['widgets']=[self.widget('chart')]
        ieee=self.sim.devices[1]['ieee'];draft['devices'][ieee].update(name='Garden sensor',freshness_seconds=600)
        saved,new=self.request('/api/v2/configuration',draft,'PUT',tag,schema='Configuration')
        self.assertNotEqual(new,tag)
        self.request('/api/v2/configuration',draft,'PUT',tag,status=412,schema='Error')
        self.request('/api/v2/configuration',draft,'PUT',status=428,schema='Error')
        self.request('/api/v1/devices/'+ieee+'/location',{'location_id':self.other['id']},'PUT')
        self.request('/api/v2/configuration',draft,'PUT',new,status=412)
        self.restart()
        doc=self.store.configuration_document()
        self.assertEqual(doc['devices'][ieee]['name'],'Garden sensor')
        self.assertEqual(doc['devices'][ieee]['location_id'],self.other['id'])
        self.assertEqual(doc['dashboard']['widgets'],saved['dashboard']['widgets'])
        self.sim.measure();self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.assertEqual(self.store.configuration_document()['revision'],doc['revision'])

    def test_validation_is_atomic_and_departed_sources_are_preserved(self):
        draft,tag=self.draft();draft['dashboard']['widgets']=[self.widget()]
        self.request('/api/v2/configuration',draft,'PUT',tag)
        original=self.store.configuration_document()
        changes=[lambda d:d['dashboard']['widgets'][0].update(position=True),
            lambda d:d['dashboard']['widgets'][0]['source'].update(endpoint=240),
            lambda d:d['devices'][self.sim.devices[1]['ieee']].update(location_id=[]),
            lambda d:d['locations'][0].update(id=[]),
            lambda d:d['dashboard']['widgets'].append(copy.deepcopy(d['dashboard']['widgets'][0])),
            lambda d:d['dashboard'].update(temperature_unit='kelvin'),
            lambda d:d['dashboard']['widgets'][0].update(title='bad\nname')]
        for mutate in changes:
            bad=copy.deepcopy(draft);mutate(bad)
            self.request('/api/v2/configuration',bad,'PUT',f'"configuration-{original["revision"]}"',status=422,schema='Error')
            self.assertEqual(self.store.configuration_document(),original)
        self.sim.devices[1]['active']=False;self.store.sync_devices(self.sim.devices)
        view=self.store.device_views()['devices'][1]
        self.assertFalse(view['registered'])
        self.assertEqual(self.store.configuration_document()['dashboard']['widgets'],original['dashboard']['widgets'])

    def test_history_pagination_ties_filters_invalids_and_cursor_restart(self):
        for value in (2100,2200,-32768,2300):
            self.sim.attr(1,1026,0x29,value)
        self.sim.emit(dict(self.sim.devices[1],type='endpoint',endpoint=2,ok=True,profile_id=260,
            device_id=770,input_clusters=[1026],output_clusters=[]))
        self.sim.emit(dict(self.sim.devices[1],type='attribute',endpoint=2,cluster=1026,attribute=0,data_type=0x29,raw=9900,rssi=-50))
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        with self.store.db:self.store.db.execute('UPDATE measurements SET received=?',(time.time(),))
        path=self.query();first,_=self.request(path,schema='History')
        self.assertIsNotNone(first['next_cursor'])
        self.request(self.query(endpoint=2,cursor=first['next_cursor']),status=400,schema='Error')
        self.request(path+'&cursor=bad',status=400)
        self.restart()
        second=self.store.measurement_history(dict(urllib.parse.parse_qsl(path.split('?',1)[1])),)
        self.assertEqual(second['next_cursor'],first['next_cursor'])
        all_items=first['items'];cursor=first['next_cursor']
        while cursor:
            page,_=self.request(path+'&cursor='+urllib.parse.quote(cursor),schema='History')
            all_items.extend(page['items']);cursor=page['next_cursor']
        self.assertEqual([p['value'] for p in all_items],[20.5,21,22,None,23])
        self.assertEqual(len({p['id'] for p in all_items}),5)
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],8)
        for changes in ({'limit':501},{'endpoint':True},{'from':'NaN'},{'to':time.time()+40*86400},{'from':time.time()+99999}):
            self.request(self.query(**changes),status=400,schema='Error')
        self.request(path+'&limit=5',status=400)

    def test_configuration_conflicts_across_store_instances(self):
        other=Store(self.path)
        try:
            draft,tag=self.draft()
            other.replace_configuration(draft,tag)
            with self.assertRaises(DashboardError) as e:self.store.replace_configuration(draft,tag)
            self.assertEqual(e.exception.status,412)
        finally:other.close()

    def test_gaps_freshness_and_history_pruning(self):
        self.store.ingest(self.sim.boot,[],self.sim.seq,self.sim.devices,gap_start=time.time()-10,gap_reason='connection_interrupted')
        page,_=self.request(self.query(),schema='History')
        self.assertEqual(page['gaps'][0]['reason'],'connection_interrupted')
        d=self.store._get(self.sim.devices[1]['ieee'])
        d['attributes']['1:1026:0']['received']=time.time()-7200
        with self.store.db:self.store._put(d)
        self.assertEqual(self.store.device_views()['devices'][1]['measurements'][0]['quality'],'stale')
        with self.store.db:self.store.db.execute('UPDATE measurements SET received=?',(time.time()-40*86400,))
        self.store.prune(30)
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],0)

    def test_auth_contracts_and_body_limits(self):
        for route in ('configuration','devices','history','capabilities','gateway','openapi.json'):
            self.request('/api/v2/'+route,token='wrong',status=401,schema='Error')
        for route,schema in (('configuration','Configuration'),('devices','Devices'),('capabilities','Capabilities'),('gateway','Gateway')):
            self.request('/api/v2/'+route,schema=schema)
        document,_=self.request('/api/v2/openapi.json')
        self.assertEqual(document,contract_v2())
        self.assertEqual(json.loads((Path(__file__).resolve().parents[1]/'docs/api/dashboard-v2.openapi.json').read_text()),document)
        for schema in document['components']['schemas'].values():Draft202012Validator.check_schema(schema)
        draft,tag=self.draft();draft['extra']='x'*65536
        self.request('/api/v2/configuration',draft,'PUT',tag,status=413,schema='Error')

    def test_backfill_from_existing_database_preserves_records(self):
        path=self.tmp.name+'/legacy.sqlite3'
        db=sqlite3.connect(path)
        db.execute('CREATE TABLE events(boot TEXT,seq INTEGER,received REAL,data TEXT,PRIMARY KEY(boot,seq))')
        events=[e for e in self.sim.events if e['type']=='attribute']
        for e in events:db.execute('INSERT INTO events VALUES(?,?,?,?)',(self.sim.boot,e['seq'],1234567890,json.dumps(e)))
        db.commit();db.close()
        store=Store(path)
        try:
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM events').fetchone()[0],3)
            self.assertEqual(store.db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],3)
            self.assertEqual(store.db.execute('SELECT MIN(received) FROM measurements').fetchone()[0],1234567890)
        finally:store.close()
        store=Store(path)
        self.assertEqual(store.db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],3);store.close()

    def test_upgrade_seeds_assigned_widgets_once_and_keeps_deleted_widgets_deleted(self):
        with self.store.db:self.store.db.execute('DROP TABLE dashboard_config')
        self.restart()
        doc=self.store.configuration_document()
        self.assertEqual(len(doc['dashboard']['widgets']),6)
        draft={k:doc[k] for k in ('locations','devices','dashboard')}
        draft['dashboard']['widgets']=[]
        self.store.replace_configuration(draft,f'"configuration-{doc["revision"]}"')
        self.restart()
        self.assertEqual(self.store.configuration_document()['dashboard']['widgets'],[])

    def test_new_device_changes_configuration_revision_but_measurements_do_not(self):
        old=self.store.configuration_document()['revision']
        self.store.sync_devices([{'ieee':'00124b0000000003','nwk':99,'active':True}])
        self.assertGreater(self.store.configuration_document()['revision'],old)
        current=self.store.configuration_document()['revision']
        self.sim.measure();self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.assertEqual(self.store.configuration_document()['revision'],current)

    def test_gap_marker_limit_is_explicit(self):
        now=time.time()
        with self.store.db:
            self.store.db.executemany('INSERT INTO ingestion_gaps(start,end,reason) VALUES(?,?,?)',
                [(now-20,now-10,'test_gap')]*501)
        page,_=self.request(self.query(),schema='History')
        self.assertEqual(len(page['gaps']),500)
        self.assertTrue(page['gaps_truncated'])


if __name__=='__main__':unittest.main()
