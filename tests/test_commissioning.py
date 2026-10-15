"""Commissioning state transitions and real authenticated HTTP integration."""
import json
import tempfile
import time
import unittest
import uuid
import urllib.error
from unittest.mock import patch
import test_api_contracts as contracts
from sbc.core import Store,validate_command
from sbc.commissioning import drive_commissioning,policy_input
from sbc.dashboard import DashboardError
from sbc.contracts_v2 import contract_v2
from jsonschema import Draft202012Validator

IEEE='00124b0000000002'
def policy(**changes):
    return dict(ieee=IEEE,endpoint=1,min_interval=5,max_interval=3600,temperature_change=.2,humidity_change=1,model_hint='SONOFF SNZB-02WD',**changes)

class CommissioningTests(contracts.ContractTests):
    # Reuse HTTP fixtures, not the parent's test cases.
    test_live_responses=None
    test_authenticated_contract_discovery=None
    test_error_responses=None
    test_exported_contracts_and_schema_validity=None
    def job(self):return self.store.commissioning_document()['jobs'][0]
    def seed(self):
        self.poller.once()
        self.store.start_commissioning(policy())
    def drain(self):
        for _ in range(12):self.poller.once()
    def test_end_to_end_verified_and_origin(self):
        self.poller.once()
        job=self.dashboard.request('/api/v2/commissioning',policy())
        self.assertEqual(job['state'],'queued')
        self.drain();job=self.job()
        self.assertEqual(job['state'],'verified');self.assertEqual(len(job['results']),6)
        self.assertEqual(job['identity'],{'manufacturer':'SONOFF','model':'SNZB-02WD'})
        doc=contract_v2();schema=dict(doc['components']['schemas']['Commissioning'],components=doc['components'])
        Draft202012Validator(schema).validate(self.dashboard.request('/api/v2/commissioning'))
        self.gateway.request('/api/v1/commands',dict(op='read',ieee=IEEE,endpoint=1,cluster=1026,attribute=0))
        self.poller.once()
        self.assertEqual(next(a for a in self.job()['measurements'] if a['cluster']==1026)['origin'],'read_response')
        self.sim.attr(1,1026,0x29,2300);self.poller.once()
        self.assertEqual(next(a for a in self.job()['measurements'] if a['cluster']==1026)['origin'],'report')
    def test_temperature_only_and_humidity_only_endpoints(self):
        self.poller.once()
        for cluster,key in [(1026,'temperature_change'),(1029,'humidity_change')]:
            with self.store.lock,self.store.db:
                device=self.store._get(IEEE)
                device['endpoints']['1']['input_clusters']=[0,32,cluster]
                self.store._put(device)
            body=policy();body.pop('humidity_change' if cluster==1026 else 'temperature_change')
            if cluster==1026:body['model_hint']='SONOFF SNZB-02LD'
            job=self.dashboard.request('/api/v2/commissioning',body)
            self.assertEqual([(s['op'],s['cluster']) for s in job['steps']],
                [('bind',32),('bind',cluster),('configure_reporting',cluster),('read_reporting',cluster)])
            self.drain();job=self.job()
            self.assertEqual(job['state'],'verified');self.assertEqual(len(job['results']),4)
            self.assertNotIn('humidity_change_raw' if cluster==1026 else 'temperature_change_raw',job['policy'])
            doc=contract_v2();schema=dict(doc['components']['schemas']['CommissioningJob'],components=doc['components'])
            Draft202012Validator(schema).validate(job)
            with self.assertRaises(DashboardError):self.store.start_commissioning(policy())
            incomplete=body.copy();incomplete.pop(key)
            with self.assertRaises(DashboardError):self.store.start_commissioning(incomplete)
            # Reopen a separate connection to verify persistence of the reduced policy.
            clone=Store(self.tmp.name+'/contract.sqlite3')
            self.assertEqual(clone.commissioning_document()['jobs'][0]['steps'],job['steps']);clone.close()
    def test_thresholds_must_match_discovered_measurements(self):
        self.poller.once()
        body=policy();body.pop('humidity_change')
        with self.assertRaises(DashboardError):self.store.start_commissioning(body)
        with self.store.lock,self.store.db:
            d=self.store._get(IEEE);d['endpoints']['1']['input_clusters']=[0,32];self.store._put(d)
        with self.assertRaises(DashboardError):self.store.start_commissioning(body)
    def test_validation_and_http_failures(self):
        self.poller.once()
        for key,value in [('min_interval',True),('max_interval',65535),('max_interval',0),('max_interval',3),('temperature_change',.001),('humidity_change',101),('model_hint','invented')]:
            body=policy();body[key]=value
            with self.assertRaises(DashboardError):policy_input(body)
        for cluster,change in [(1026,32768),(1029,10001)]:
            with self.assertRaises(ValueError):validate_command(dict(op='configure_reporting',ieee=IEEE,endpoint=1,request_id=str(uuid.uuid4()),cluster=cluster,attribute=0,min_interval=5,max_interval=3600,reportable_change=change))
        self.dashboard.request('/api/v2/commissioning',policy())
        with self.assertRaises(urllib.error.HTTPError) as e:self.dashboard.request('/api/v2/commissioning',policy())
        self.assertEqual(e.exception.code,409)
        self.assertEqual(self.dashboard.request('/api/v2/commissioning',{'ieee':IEEE,'action':'cancel'})['state'],'cancelled')
        with self.assertRaises(urllib.error.HTTPError) as e:
            from sbc.core import Gateway
            Gateway(self.dashboard.url,'wrong').request('/api/v2/commissioning')
        self.assertEqual(e.exception.code,401)
    def test_readback_unsupported_and_mismatch(self):
        self.sim.reporting_failures[('read_reporting',1026)]=0x82
        self.seed();self.drain();self.assertEqual(self.job()['state'],'configured_unverified')
        job=self.store.start_commissioning(policy());self.poller.once();self.poller.once()
        # Configuration acknowledgement is not proof of readback agreement.
        self.sim.reporting[(IEEE,1,1026)]={'min_interval':5,'max_interval':100,'reportable_change':20}
        self.poller.once()
        # A separate deterministic mismatched readback response.
        job=self.job();job.update(state='sending',step=2,attempt=1,request_id='mismatch')
        with self.store.lock,self.store.db:self.store._save_job(job)
        event=dict(type='commissioning',ieee=IEEE,nwk=0x2345,seq=1000,endpoint=1,cluster=1026,operation='read_reporting',phase='response',status=0,request_id='mismatch',min_interval=5,max_interval=2,reportable_change=20,data_type=0x29)
        self.store.ingest(self.sim.boot,[event],1000)
        self.assertEqual(self.job()['state'],'waiting');self.assertIn('differs',self.job()['message'])
    def test_timeout_backoff_expiry_and_reboot(self):
        self.seed();now=time.time();health={'boot_id':self.sim.boot,'reporting_commissioning':True}
        class Silent:
            def request(self,*args):return {'accepted':True}
        silent=Silent();drive_commissioning(self.store,silent,health,now)
        job=self.job();rid=job['request_id'];self.assertEqual(job['attempt'],1)
        drive_commissioning(self.store,silent,health,now+28);self.assertEqual(self.job()['state'],'waiting')
        drive_commissioning(self.store,silent,health,now+29);self.assertEqual(self.job()['attempt'],1)
        # A late response to a superseded attempt cannot advance the workflow.
        e=dict(type='commissioning',ieee=IEEE,nwk=0x2345,seq=999,endpoint=1,cluster=1026,operation='bind',phase='response',status=0,request_id=rid)
        self.store.ingest(self.sim.boot,[e],999);self.assertEqual(self.job()['step'],0)
        drive_commissioning(self.store,silent,health,now+301);self.assertEqual(self.job()['state'],'expired')
        # Existing policy stays durable across reopening SQLite.
        clone=Store(self.tmp.name+'/contract.sqlite3')
        self.assertEqual(clone.commissioning_document()['jobs'][0]['policy']['temperature_change_raw'],20);clone.close()
        job=self.job();job.update(state='verified',gateway_boot='old')
        with self.store.lock,self.store.db:self.store._save_job(job)
        drive_commissioning(self.store,silent,health,now+400)
        self.assertEqual(self.job()['state'],'sending');self.assertEqual(self.job()['attempt'],1)
    def test_three_attempt_limit_and_checkin_wakeup(self):
        self.seed();now=time.time();health={'boot_id':self.sim.boot,'reporting_commissioning':True}
        class Silent:
            def request(self,*args):return {'accepted':True}
        silent=Silent()
        for delta in (0,28,58,86,116,144):drive_commissioning(self.store,silent,health,now+delta)
        self.assertEqual(self.job()['state'],'failed');self.assertEqual(self.job()['attempt'],3)
        drive_commissioning(self.store,silent,health,now+200)
        self.assertEqual(self.job()['attempt'],3)
        self.store.start_commissioning(policy(),now=now+201)
        drive_commissioning(self.store,silent,health,now+201)
        drive_commissioning(self.store,silent,health,now+229)
        with patch('sbc.core.time.time',return_value=now+230):
            self.store.ingest(self.sim.boot,[dict(type='check_in',ieee=IEEE,nwk=0x2345,seq=500)],500)
        drive_commissioning(self.store,silent,health,now+230)
        self.assertEqual(self.job()['attempt'],2)
    def test_uncertain_http_submission_keeps_remote_correlation(self):
        self.seed();owner=self
        class LostResponse:
            def request(self,path,body):
                result=owner.sim.command(body)
                raise OSError('HTTP response lost after transmission')
        drive_commissioning(self.store,LostResponse(),{'boot_id':self.sim.boot,'reporting_commissioning':True})
        self.assertEqual(self.job()['state'],'sending')
        cursor=self.store.cursor()[1]
        self.store.ingest(self.sim.boot,[e for e in self.sim.events if e['seq']>cursor],self.sim.seq)
        self.assertEqual(self.job()['step'],1);self.assertEqual(self.job()['attempt'],0)
    def test_no_false_contact_or_retry_after_cancel(self):
        self.seed();before=self.store._get(IEEE).get('last_seen')
        self.store.ingest(self.sim.boot,[dict(type='commissioning',ieee=IEEE,nwk=0x2345,seq=999,phase='timeout')],999)
        self.assertEqual(self.store._get(IEEE).get('last_seen'),before)
        self.store.cancel_commissioning(IEEE)
        class Never:
            def request(self,*a):raise AssertionError('cancelled job must not send')
        drive_commissioning(self.store,Never(),{'boot_id':'other','reporting_commissioning':True})
        self.assertEqual(self.job()['state'],'cancelled')
