"""Synthetic S60ZBTPG preparation; no hardware claims."""
import copy
import json
import time
import unittest
import urllib.error
from unittest.mock import patch
from decimal import Decimal
from jsonschema import Draft202012Validator
import test_api_contracts as base
from sbc import plugs
from sbc.core import Store,normalize
from sbc.dashboard import DashboardError
from sbc.plug_jobs import drive_plugs
from sbc.contracts_v2 import contract_v2

IEEE='00124b0000000027'
class PlugTests(base.ContractTests):
    test_live_responses=None
    test_authenticated_contract_discovery=None
    test_error_responses=None
    test_exported_contracts_and_schema_validity=None
    def add(self):
        self.sim.add_s60zbtpg()
        while self.poller.once():pass
    def start(self,action,settings=None):return self.store.start_plug(dict(ieee=IEEE,endpoint=1,action=action,settings=settings or {}))
    def job(self):return self.store.plug_document()['jobs'][0]
    def drive(self,n=70):
        now=time.time()+4
        for i in range(n):
            drive_plugs(self.store,self.gateway,dict(ready=True,plug_extensions=True,boot_id=self.sim.boot),now+i*4)
            # Ingest without driving the real-time worker twice in this synthetic clock.
            cursor=self.store.cursor()[1];events=[e for e in self.sim.events if e['seq']>cursor]
            self.store.ingest(self.sim.boot,events,self.sim.seq,self.sim.devices)
            if self.job()['state'] not in ('queued','sending','waiting'):break
    def schema(self,name,value):
        doc=contract_v2();schema=dict(doc['components']['schemas'][name],components=doc['components'])
        Draft202012Validator(json.loads(json.dumps(schema),parse_float=Decimal)).validate(json.loads(json.dumps(value),parse_float=Decimal))
    def test_profile_does_not_create_device_or_command(self):
        self.poller.once();before=self.store.snapshot()
        d=self.dashboard.request('/api/v2/plug-profiles');self.schema('PlugProfiles',d)
        self.assertEqual(d['hardware_status'],'not_tested');self.assertEqual(self.store.snapshot(),before)
        self.assertEqual(self.dashboard.request('/api/v2/plugs'),{'jobs':[]})
    def test_composite_wire_boundaries_and_no_14_amp(self):
        raw=plugs.protection({'max_current':13,'max_power':3250});self.assertEqual(raw,'040b010001c832000050973100')
        self.assertEqual(plugs.decode_protection(raw),{'max_current':13,'max_power':3250})
        full=dict(max_current=12,max_power=3000,enable_min_current=True,min_current=.1,enable_max_voltage=True,max_voltage=260,enable_min_voltage=True,min_voltage=200,enable_min_power=True,min_power=1)
        payload=plugs.protection(full);self.assertEqual(len(bytes.fromhex(payload)),29);self.assertEqual(plugs.decode_protection(payload)['min_voltage'],200)
        for bad in [dict(max_current=14,max_power=3250),dict(max_current=True,max_power=3250),dict(max_current=13,max_power=3250,enable_min_current=True),dict(max_current=13,max_power=3250,min_current=.1),dict(max_current=13,max_power=3250,enable_min_current=True,min_current=13),dict(max_current=float('nan'),max_power=3250),dict(max_current=1.23,max_power=3250)]:
            with self.assertRaises(DashboardError):plugs.protection(bad)
        for secs in (.5,3599.5):
            p=plugs.inching(dict(enabled=True,mode='off',seconds=secs));self.assertEqual(len(bytes.fromhex(p)),11)
            c=dict(op='plug_inching',ieee=IEEE,endpoint=1,request_id='a'*36,cluster=64529,attribute=0,payload=p);plugs.validate_command(c)
            c['payload']=p[:-2]+'ff'
            with self.assertRaises(ValueError):plugs.validate_command(c)
        for secs in (0,.1,3600,True):
            with self.assertRaises(DashboardError):plugs.inching(dict(enabled=True,mode='off',seconds=secs))
    def test_commission_reads_reports_scaling_without_switching(self):
        self.add();before=dict(self.sim.plug_values);j=self.start('commission');self.schema('PlugJob',j);self.drive();self.assertEqual(self.job()['state'],'verified');self.assertEqual(before,self.sim.plug_values)
        self.assertEqual(len(self.sim.reporting),len(plugs.REPORTS))
        d=next(d for d in self.store.device_views()['devices'] if d['ieee']==IEEE);self.assertEqual(d['profile'],plugs.MODEL);self.schema('Devices',self.store.device_views())
        values={m['label']:m['value'] for m in d['measurements']};self.assertEqual(values['Accumulated energy'],123456789.012);self.assertEqual(values['Active power'],230)
        self.assertNotIn('Temperature',values);self.assertNotIn('Battery',values)
        self.schema('PlugJobs',self.store.plug_document())
    def test_relay_not_optimistic_and_raw_off_values_preserved(self):
        self.add();j=self.start('relay',{'state':False});self.assertIs(self.store._get(IEEE)['attributes']['1:6:0']['value'],True)
        with self.assertRaises(DashboardError):self.start('read')
        self.drive();self.assertEqual(self.job()['state'],'verified');d=next(d for d in self.store.device_views()['devices'] if d['ieee']==IEEE)
        self.assertEqual(d['plug']['effective_off']['power_w'],0)
        self.assertEqual(next(m['value'] for m in d['measurements'] if m['label']=='Active power'),230)
        self.assertEqual(next(m['value'] for m in d['measurements'] if m['label']=='Voltage'),230)
        self.assertIs(self.store._get(IEEE)['attributes']['1:6:0']['value'],False)
    def test_settings_readback_inching_ack_and_rejection(self):
        self.add()
        for action,settings in [('startup_behavior',{'value':'previous'}),('network_indicator',{'value':False}),('outlet_protection',{'value':True}),('protection',{'max_current':10,'max_power':2000})]:
            self.start(action,settings);self.drive();self.assertEqual(self.job()['state'],'verified')
        self.start('inching',dict(enabled=True,mode='off',seconds=1));self.drive();self.assertEqual(self.job()['state'],'acknowledged_unverified')
        self.sim.plug_failures[('plug_write',64529,1)]=0x87;self.start('network_indicator',{'value':True});self.drive();self.assertEqual(self.job()['state'],'failed')
    def test_uncertain_write_never_replayed_and_restart_cancel(self):
        self.add();self.start('relay',{'state':False});now=time.time()+5;health=dict(ready=True,plug_extensions=True,boot_id=self.sim.boot)
        with patch.object(self.gateway,'request',side_effect=TimeoutError) as calls:
            drive_plugs(self.store,self.gateway,health,now);drive_plugs(self.store,self.gateway,health,now+4)
            rid=self.job()['request_id'];self.assertIsNotNone(rid)
            drive_plugs(self.store,self.gateway,health,now+40);drive_plugs(self.store,self.gateway,health,now+90)
            self.assertEqual(self.job()['state'],'uncertain');self.assertEqual(sum(1 for c in calls.call_args_list if c.args[1].get('op')=='plug_relay'),1)
        self.start('relay',{'state':True});self.store._init_plugs();self.assertEqual(self.job()['state'],'cancelled')
        self.start('read');self.store._init_plugs();self.assertEqual(self.job()['state'],'queued')
    def test_wrong_correlation_and_mismatched_readback_rejected(self):
        self.add();self.start('relay',{'state':False});now=time.time()+5;health=dict(ready=True,plug_extensions=True,boot_id=self.sim.boot)
        with patch.object(self.gateway,'request',return_value={'accepted':True}):
            drive_plugs(self.store,self.gateway,health,now);drive_plugs(self.store,self.gateway,health,now+4)
        j=self.job();e=dict(type='commissioning',ieee=IEEE,nwk=0x3427,endpoint=1,cluster=6,attribute=0,request_id=j['request_id'],operation='plug_relay',phase='response',status=0)
        with self.store.lock,self.store.db:
            self.store.plug_event('wrong-boot',e,now);self.assertEqual(self.job()['step'],0)
            self.store.plug_event(self.sim.boot,dict(e,endpoint=2),now);self.assertEqual(self.job()['step'],0)
            self.store.plug_event(self.sim.boot,e,now)
        with patch.object(self.gateway,'request',return_value={'accepted':True}):drive_plugs(self.store,self.gateway,health,now+8)
        j=self.job();e.update(request_id=j['request_id'],operation='plug_read',raw=1,data_type=0x10)
        with self.store.lock,self.store.db:self.store.plug_event(self.sim.boot,e,now+9)
        self.assertEqual(self.job()['state'],'failed')
    def test_unknown_scaling_invalid_sentinels_and_counter_reset(self):
        self.add();d=self.store._get(IEEE)
        self.assertEqual(normalize(1794,0,0x25,123456789012,d,1),(123456789.012,'kWh'))
        broken=copy.deepcopy(d);broken['attributes'].pop('1:1794:770')
        self.assertEqual(normalize(1794,0,0x25,10,broken,1),(None,None))
        for c,a,t,v in [(1794,0,0x25,0xffffffffffff),(64529,0x7004,0x23,0xffffffff),(64529,0x7004,0x21,1)]:self.assertEqual(normalize(c,a,t,v,d,1),(None,None))
        self.sim.attr(2,1794,0x25,5,0);self.poller.once();view=next(d for d in self.store.device_views()['devices'] if d['ieee']==IEEE)
        self.assertEqual(view['plug']['energy_discontinuities'][0]['reason'],'counter_decrease_reset_or_rollover')
        self.assertEqual(next(m['value'] for m in view['measurements'] if m['label']=='Accumulated energy'),.005)
        self.sim.attr(2,64529,0x23,0,0x7004);self.poller.once();self.assertEqual(self.store._get(IEEE)['attributes']['1:64529:28676']['value'],0)
    def test_api_auth_sensors_rejected_unknown_fields_and_shared_jobs(self):
        self.add();body=dict(ieee=IEEE,endpoint=1,action='relay',settings={'state':False});self.schema('PlugInput',body)
        for bad,status in [(dict(body,ieee='00124b0000000002'),422),(dict(body,extra=1),422),(dict(body,endpoint=True),422)]:
            with self.assertRaises(urllib.error.HTTPError) as e:self.dashboard.request('/api/v2/plugs',bad)
            self.assertEqual(e.exception.code,status)
        wrong=base.Gateway(self.dashboard.url,'wrong')
        for path in ('/api/v2/plugs','/api/v2/plug-profiles'):
            with self.assertRaises(urllib.error.HTTPError) as e:wrong.request(path)
            self.assertEqual(e.exception.code,401)
        j=self.dashboard.request('/api/v2/plugs',body);self.schema('PlugJob',j)
        with self.assertRaises(urllib.error.HTTPError) as e:self.dashboard.request('/api/v1/commands',dict(op='on_off',ieee=IEEE,endpoint=1,state=True))
        self.assertEqual(e.exception.code,400)
        self.dashboard.request('/api/v2/plugs',{'job_id':j['id'],'action':'cancel'});self.assertEqual(self.job()['state'],'cancelled')
    def test_model_hint_does_not_grant_control_and_variant_rejected(self):
        self.add();d=self.store._get(IEEE);d['attributes']['1:0:5']['raw']='S60ZBTPF'
        with self.store.lock,self.store.db:self.store._put(d)
        with self.assertRaises(DashboardError):self.start('relay',{'state':True})
        self.assertFalse(plugs.identified(d));self.assertIsNone(self.store.plug_details(d))

    def test_meter_history_profile_layouts_and_source_ages(self):
        self.add();location=self.store.save_location('Plug bench');self.store.assign_location(IEEE,location['id'])
        profile=self.store.save_profile({'name':'Plug viewer'})['id'];before=self.store.configuration_document();doc=self.store.configuration_document(profile)
        body={k:copy.deepcopy(doc[k]) for k in ('locations','devices','dashboard')}
        body['dashboard']['widgets']=[dict(id='power-chart',type='chart',title='Power',position=0,time_range=86400,source=dict(ieee=IEEE,endpoint=1,cluster=64529,attribute=0x7006)),dict(id='relay-now',type='numeric',title='State',position=1,time_range=86400,source=dict(ieee=IEEE,endpoint=1,cluster=6,attribute=0))]
        body['dashboard']['all_layout']={'columns':2,'min_tile_width':240,'order':[IEEE]}
        self.store.replace_configuration(body,self.store.configuration_etag(profile),profile)
        self.assertEqual(self.store.configuration_document(),before);self.assertEqual(len(self.store.configuration_document(profile)['dashboard']['widgets']),2)
        self.sim.attr(2,64529,0x23,125000,0x7006);self.poller.once()
        now=time.time();q=dict(ieee=IEEE,endpoint='1',cluster='64529',attribute=str(0x7006),**{'from':str(now-3600),'to':str(now+10),'limit':'1'})
        first=self.store.measurement_history(q);self.assertTrue(first['next_cursor']);second=self.store.measurement_history(dict(q,cursor=first['next_cursor']))
        self.assertNotEqual(first['items'][0]['id'],second['items'][0]['id']);self.assertEqual({first['items'][0]['value'],second['items'][0]['value']},{125,230})
        self.assertTrue(all('rssi' in x for x in first['items']));self.assertEqual(self.store.db.execute('pragma integrity_check').fetchone()[0],'ok')
        with self.assertRaises(DashboardError):self.store.measurement_history(dict(q,limit='501'))
        d=self.store._get(IEEE);d['attributes']['1:1794:768']['raw']=1
        self.assertEqual(normalize(1794,0,0x25,10,d,1),(None,None))
    def test_read_timeouts_are_bounded_and_boot_change_makes_write_uncertain(self):
        self.add();self.start('read');health=dict(ready=True,plug_extensions=True,boot_id=self.sim.boot);now=time.time()+5
        with patch.object(self.gateway,'request',side_effect=TimeoutError) as calls:
            for offset in (0,4,32,38,66,72,100):drive_plugs(self.store,self.gateway,health,now+offset)
            self.assertEqual(self.job()['state'],'failed');self.assertEqual(sum(1 for c in calls.call_args_list if c.args[1]['op']=='plug_read'),3)
        self.start('relay',{'state':False})
        with patch.object(self.gateway,'request',return_value={'accepted':True}):
            drive_plugs(self.store,self.gateway,health,now);drive_plugs(self.store,self.gateway,health,now+4)
            drive_plugs(self.store,self.gateway,dict(health,boot_id='new-boot'),now+5)
        self.assertEqual(self.job()['state'],'uncertain')
