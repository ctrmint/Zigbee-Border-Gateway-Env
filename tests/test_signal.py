"""RSSI migration, event correlation, retention and passive API coverage."""
import copy
import json
import sqlite3
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from jsonschema import Draft202012Validator
from sbc.core import Store, Poller, validate_command
from sbc.app import make_handler
from sbc.dashboard import DashboardError
from sbc.contracts_v2 import contract_v2
from sbc.simulator import Simulation


class SignalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.path = self.tmp.name+'/signal.sqlite3'
        self.store = Store(self.path); self.addCleanup(lambda: self.store.close())
        self.sim = Simulation()
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.ieee = self.sim.devices[1]['ieee']
        self.seq = self.sim.seq + 1

    def event(self, rssi=-82, **extra):
        e=dict(type='attribute',ieee=self.ieee,nwk=123,endpoint=1,cluster=1026,
               attribute=0,data_type=41,raw=1400,origin='report',seq=self.seq,rssi=rssi)
        e.update(extra);self.seq+=1;return e

    def query(self, **extra):
        q=dict(ieee=self.ieee,endpoint='1',cluster='65535',attribute='0',limit='500',
               **{'from':str(time.time()-3600),'to':str(time.time()+10)})
        q.update(extra);return q

    def view(self):return next(d for d in self.store.device_views()['devices'] if d['ieee']==self.ieee)['signal']

    def test_correlation_duplicate_and_new_gateway_boot(self):
        e=self.event();self.store.ingest('first',[e],e['seq']);n=self.store.db.execute('select count(*) from signal_samples').fetchone()[0]
        self.store.ingest('first',[e],e['seq']);self.assertEqual(n,self.store.db.execute('select count(*) from signal_samples').fetchone()[0])
        history=self.store.measurement_history(self.query());sample=history['items'][-1]
        self.assertEqual((sample['value'],sample['boot_id'],sample['seq'],sample['origin']),(-82,'first',e['seq'],'report'))
        m=self.store.measurement_history(self.query(cluster='1026'))['items'][-1]
        self.assertEqual((m['rssi'],m['boot_id'],m['seq']),(-82,'first',e['seq']))
        self.store.ingest('second',[dict(e,rssi=-60)],e['seq'])
        self.assertEqual(self.view()['value'],-60)
        self.assertEqual(len(self.store.measurement_history(self.query())['items']),len(history['items'])+1)

    def test_invalid_missing_and_non_attribute_events(self):
        for value in (None,True,127,128,-129,-60.5,'-60'):
            e=self.event(value);self.store.ingest('invalid',[e],e['seq'])
        self.assertNotEqual(self.view()['boot_id'],'invalid')
        e=self.event(-75,type='check_in');e.pop('endpoint');e.pop('cluster');e.pop('attribute')
        self.store.ingest('checkin',[e],e['seq'])
        self.assertEqual(self.view()['value'],-75);self.assertIsNone(self.view()['source_endpoint'])
        # A sensor with no RSSI remains selectable for signal history, without fabricated samples.
        other=self.sim.devices[0]['ieee']
        self.store.db.execute('delete from signal_latest where ieee=?',(other,));self.store.db.commit()
        v=next(d for d in self.store.device_views()['devices'] if d['ieee']==other)['signal']
        self.assertEqual((v['value'],v['quality']),(None,'missing'))
        with self.assertRaises(ValueError):validate_command(dict(op='read',ieee=self.ieee,endpoint=1,cluster=65535,attribute=0))

    def test_migration_restart_and_preservation(self):
        before=self.store.configuration_document()
        e=self.event(-81);self.store.ingest('backfill',[e],e['seq'])
        # Rehearse upgrade from the pre-signal schema with retained raw events.
        for table in ('signal_samples','signal_latest','signal_migration'):self.store.db.execute('drop table '+table)
        self.store.db.commit();self.store.close();self.store=Store(self.path)
        self.assertEqual(self.view()['value'],-81)
        self.assertEqual(self.store.configuration_document(),before)
        n=self.store.db.execute('select count(*) from signal_samples').fetchone()[0]
        self.store.close();self.store=Store(self.path)
        self.assertEqual(n,self.store.db.execute('select count(*) from signal_samples').fetchone()[0])
        self.assertEqual(self.store.db.execute('pragma integrity_check').fetchone()[0],'ok')

    def test_retention_keeps_last_known_signal_stale(self):
        old=time.time()-31*86400;e=self.event(-84)
        with self.store.db:self.store._record_signal('old',e,old)
        self.store.db.execute('delete from signal_samples where boot!=?',('old',))
        self.store.db.execute('delete from signal_latest');self.store.db.commit()
        with self.store.db:self.store._record_signal('old',e,old)
        self.store.prune(30)
        self.assertEqual(self.store.db.execute('select count(*) from signal_samples').fetchone()[0],0)
        self.assertEqual((self.view()['value'],self.view()['quality']),(-84,'stale'))
        self.store.close();self.store=Store(self.path)
        self.assertEqual(self.view()['quality'],'stale')

    def test_bounded_history_cursor_and_profile_widgets(self):
        for rssi in (-82,-80,-78):
            e=self.event(rssi);self.store.ingest('pages',[e],e['seq'])
        q=self.query(limit='1');first=self.store.measurement_history(q)
        self.assertTrue(first['next_cursor']);second=self.store.measurement_history(dict(q,cursor=first['next_cursor']))
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id'])
        for changes in ({'endpoint':'2'},{'attribute':'1'},{'limit':'501'},{'from':'0','to':str(time.time())},{'ieee':self.sim.devices[0]['ieee'],'cursor':first['next_cursor']}):
            with self.assertRaises(DashboardError):self.store.measurement_history(dict(q,**changes))
        location=self.store.save_location('Signal test');self.store.assign_location(self.ieee,location['id'])
        profile=self.store.save_profile({'name':'Signal viewer'})
        pid=profile['id'];before=self.store.configuration_document()
        c=self.store.configuration_document(pid);body={k:copy.deepcopy(c[k]) for k in ('locations','devices','dashboard')}
        body['dashboard']['widgets']=[dict(id='signal-chart',type='chart',title='Signal',position=0,time_range=86400,source=dict(ieee=self.ieee,endpoint=1,cluster=65535,attribute=0))]
        self.store.replace_configuration(body,self.store.configuration_etag(pid),pid)
        self.assertEqual(self.store.configuration_document(),before)
        self.assertEqual(self.store.configuration_document(pid)['dashboard']['widgets'][0]['source']['cluster'],65535)

    def test_authenticated_schema_and_no_radio_commands(self):
        poller=Poller(None,self.store);poller.status.update(connected=True,ready=True)
        server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,poller,None,'s'*64))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            root='http://127.0.0.1:'+str(server.server_port)
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(root+'/api/v2/devices')
            self.assertEqual(caught.exception.code,401)
            with patch('sbc.core.Gateway.request',side_effect=AssertionError('Unexpected radio request')):
                for path,name in (('/api/v2/devices','Devices'),('/api/v2/history?'+__import__('urllib.parse').parse.urlencode(self.query()),'History')):
                    req=urllib.request.Request(root+path,headers={'Authorization':'Bearer '+'s'*64})
                    with urllib.request.urlopen(req) as response:data=json.load(response)
                    doc=contract_v2();Draft202012Validator(dict(doc['components']['schemas'][name],components=doc['components'])).validate(data)
        finally:server.shutdown();server.server_close();thread.join()
