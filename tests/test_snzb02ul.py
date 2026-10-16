"""Synthetic UL preparation; none of these tests establishes RF compatibility."""
import json
import time
import urllib.error
import unittest
from unittest.mock import patch
from decimal import Decimal
from jsonschema import Draft202012Validator
import test_api_contracts as contracts
from sbc.core import Store,normalize,validate_command
from sbc.sensors import UL,REFERENCE_REVISION,profile_document,display_settings,remote_display_payload,weather_reply_payload,zigbee_time
from sbc.dashboard import DashboardError
from sbc.display import drive_display,drive_clock
from sbc.commissioning import drive_commissioning
from sbc.contracts_v2 import contract_v2

IEEE='00124b0000000014'
def policy():return {'ieee':IEEE,'endpoint':1,'min_interval':5,'max_interval':1800,'temperature_change':.2,'humidity_change':1,'model_hint':UL}

class ULTests(contracts.ContractTests):
    test_live_responses=None
    test_authenticated_contract_discovery=None
    test_error_responses=None
    test_exported_contracts_and_schema_validity=None
    def add(self,**kwargs):
        self.sim.add_snzb02ul(**kwargs)
        for _ in range(3):self.poller.once()
    def job(self):return next(j for j in self.store.commissioning_document()['jobs'] if j['ieee']==IEEE)
    def display(self):return self.store.display_document()['jobs'][0]
    def drain(self,n=18):
        for _ in range(n):self.poller.once()
    def schema(self,name,value):
        doc=contract_v2();schema=dict(doc['components']['schemas'][name],components=doc['components'])
        # JSON Schema multipleOf is decimal arithmetic; binary floats misclassify -1.2/0.1.
        Draft202012Validator(json.loads(json.dumps(schema),parse_float=Decimal)).validate(json.loads(json.dumps(value),parse_float=Decimal))
    def test_preparation_metadata_does_not_create_devices(self):
        self.poller.once();before=self.store.snapshot()
        doc=self.dashboard.request('/api/v2/sensor-profiles');self.schema('SensorProfiles',doc)
        self.assertEqual(doc['reference_revision'],REFERENCE_REVISION)
        ul=next(p for p in doc['profiles'] if p['model']==UL)
        self.assertEqual(ul['defaults']['max_interval'],1800);self.assertEqual(ul['hardware_status'],'not_tested')
        self.assertEqual(self.store.snapshot(),before)
    def test_observed_ul_with_blank_hint_probes_battery(self):
        self.add()
        request=policy();request['model_hint']=''
        job=self.store.start_commissioning(request)
        self.assertEqual(job['model_profile'],UL)
        with patch.object(self.gateway,'request',wraps=self.gateway.request) as calls:
            self.poller.once()
        probes=[c.args[1] for c in calls.call_args_list if len(c.args)>1 and isinstance(c.args[1],dict) and c.args[1].get('op')=='read' and c.args[1].get('cluster')==1]
        self.assertEqual({c['attribute'] for c in probes},{32,33})

    def test_profile_commissioning_battery_and_optional_failure(self):
        self.add(voltage=False)
        self.sim.reporting_failures[('bind',6)]=0x84
        self.sim.reporting_failures[('configure_reporting',1)]=0x86
        j=self.dashboard.request('/api/v2/commissioning',policy())
        self.assertTrue(any(s['cluster']==6 and s['optional'] for s in j['steps']))
        self.drain();j=self.job();self.assertEqual(j['state'],'verified');self.assertTrue(j['warnings'])
        self.schema('CommissioningJob',j)
        view=next(v for v in self.store.device_views()['devices'] if v['ieee']==IEEE)
        self.assertEqual(view['profile'],UL)
        battery=next(m for m in view['measurements'] if m['cluster']==1)
        self.assertEqual(battery['value'],80);self.assertEqual(battery['freshness_seconds'],172800)
        self.assertFalse(any(m['cluster']==1 and m['attribute']==32 for m in view['measurements']))
        self.assertFalse(any(m['cluster']==6 for m in view['measurements']))
        # A binding requirement must not create appliance commands.
        with self.assertRaises(urllib.error.HTTPError) as e:self.dashboard.request('/api/v1/commands',{'op':'on_off','ieee':IEEE,'endpoint':1,'state':True})
        self.assertEqual(e.exception.code,400)
        original=self.store.snapshot()[0]['ieee'];self.assertNotEqual(original,IEEE)
    def test_battery_scaling_unknowns_freshness_low_and_history(self):
        for cluster,attr,dtype,raw,value,unit in [(1,33,32,101,50.5,'%'),(1,32,32,30,3,'V'),(1,33,32,255,None,None),(1,32,32,255,None,None),(1,33,32,201,None,None),(1,33,33,100,None,None)]:
            self.assertEqual(normalize(cluster,attr,dtype,raw),(value,unit))
        self.add(voltage=True)
        self.sim.attr(2,1,32,30,33);self.poller.once()
        with self.store.lock,self.store.db:
            d=self.store._get(IEEE);d['attributes']['1:1:33']['received']=time.time()-7200;d['attributes']['1:1026:0']['received']=time.time()-7200;self.store._put(d)
        m=next(d for d in self.store.device_views()['devices'] if d['ieee']==IEEE)['measurements']
        battery=next(a for a in m if a['cluster']==1 and a['attribute']==33)
        self.assertTrue(battery['low_battery']);self.assertEqual(battery['quality'],'valid')
        self.assertEqual(next(a for a in m if a['cluster']==1026)['quality'],'stale')
        q={'ieee':IEEE,'endpoint':'1','cluster':'1','attribute':'33','from':str(time.time()-3600),'to':str(time.time()+1)}
        hist=self.store.measurement_history(q);self.assertEqual(hist['items'][-1]['value'],15)
        self.validate('dashboard','State',self.dashboard.request('/api/v1/state'))
    def test_scalar_display_write_readback_and_persistence(self):
        self.add();body={'ieee':IEEE,'endpoint':1,'settings':{'temperature_units':'fahrenheit','comfort_temperature_min':19.5,'temperature_calibration':-1.2}}
        j=self.dashboard.request('/api/v2/display',body);self.assertEqual(j['state'],'queued')
        self.drain();self.assertEqual(self.display()['state'],'verified')
        self.schema('DisplayJobs',self.dashboard.request('/api/v2/display'))
        self.assertEqual(self.sim.display_values[(IEEE,4)],1950)
        self.assertEqual(self.sim.display_values[(IEEE,0x2003)],-120)
        clone=Store(self.tmp.name+'/contract.sqlite3');self.assertEqual(clone.display_document(),self.store.display_document());clone.close()
        # Display settings never masquerade as measured sensor history.
        self.assertFalse(self.store.db.execute('SELECT 1 FROM measurements WHERE cluster=64529').fetchone())
    def test_display_rejection_validation_cancel_and_busy(self):
        self.add()
        for settings in ({'foo':1},{'temperature_units':True},{'comfort_temperature_min':50.1},{'humidity_calibration':.01},{'comfort_temperature_min':30,'comfort_temperature_max':20}):
            with self.assertRaises(DashboardError):display_settings(settings)
        self.store.start_display({'ieee':IEEE,'endpoint':1,'settings':{'temperature_units':'celsius'}})
        with self.assertRaises(DashboardError):self.store.start_commissioning(policy())
        self.store.cancel_display(IEEE)
        self.sim.display_failures[('write_display',7)]=0x86
        self.store.start_display({'ieee':IEEE,'endpoint':1,'settings':{'temperature_units':'fahrenheit'}})
        # Three attempts, delivered rejection each time; bounded stop.
        self.poller.once();self.poller.once()
        for _ in range(2):
            j=self.display();j['next_attempt']=time.time()-1
            with self.store.lock,self.store.db:self.store._save_display(j)
            self.poller.once();self.poller.once()
        self.assertEqual(self.display()['state'],'failed')
        self.assertEqual(self.sim.display_values[(IEEE,7)],0)
    def test_missing_vendor_and_auth_old_firmware(self):
        self.add(vendor_cluster=False)
        with self.assertRaises(DashboardError):self.store.start_display({'ieee':IEEE,'endpoint':1,'settings':{'temperature_units':'celsius'}})
        from sbc.core import Gateway
        for path in ('sensor-profiles','display'):
            with self.assertRaises(urllib.error.HTTPError) as e:Gateway(self.dashboard.url,'wrong').request('/api/v2/'+path)
            self.assertEqual(e.exception.code,401)
        self.poller.status['sensor_extensions']=False
        with self.assertRaises(urllib.error.HTTPError) as e:self.dashboard.request('/api/v2/commissioning',policy())
        self.assertEqual(e.exception.code,503)
        observed=policy();observed['model_hint']=''
        with self.assertRaises(urllib.error.HTTPError) as e:self.dashboard.request('/api/v2/commissioning',observed)
        self.assertEqual(e.exception.code,503)
    def test_clock_lease_epoch_offset_and_reboot_resync(self):
        self.add();self.assertIsNotNone(self.sim.clock)
        self.assertEqual(zigbee_time(946684800),0)
        with self.assertRaises(DashboardError):zigbee_time(946684799)
        with self.assertRaises(DashboardError):zigbee_time(946684800+0xffffffff)
        old=self.poller.clock_synced
        drive_clock(self.poller,dict(self.poller.status));self.assertEqual(old,self.poller.clock_synced)
        self.sim.boot='new-ul-boot';self.poller.once();self.assertEqual(self.poller.clock_synced[0],self.sim.boot)
        self.assertTrue(-50400<=self.sim.clock['utc_offset']<=50400)
        self.assertEqual(self.sim.clock['unix_time']-946684800,zigbee_time(self.sim.clock['unix_time']))
    def test_prepared_remote_weather_codecs_and_no_telemetry(self):
        self.assertEqual(remote_display_payload('temperature',-1.2),bytes.fromhex('0101000307010000010288ff'))
        self.assertEqual(remote_display_payload('humidity',50),bytes.fromhex('010100030701010001028813'))
        self.assertEqual(remote_display_payload('all',None,False),bytes.fromhex('010100030d03000000000100000002000000'))
        self.assertEqual(weather_reply_payload(bytes(9),'snow'),bytes([0,1,4]))
        for call in (lambda:remote_display_payload('pressure',1200),lambda:remote_display_payload('temperature',float('nan')),lambda:weather_reply_payload(b'\x00','rain'),lambda:weather_reply_payload(bytes(9),'invented')):
            with self.assertRaises(DashboardError):call()
        self.assertEqual(self.store.db.execute('SELECT COUNT(*) FROM measurements').fetchone()[0],0)
    def test_optional_expiry_does_not_mask_core_failure_after_reboot(self):
        self.add();self.store.start_commissioning(policy());self.drain()
        j=self.job();self.assertEqual(j['state'],'verified');self.assertTrue(j['core_verified'])
        now=time.time()
        class Silent:
            def request(self,*a):return {'accepted':True}
        drive_commissioning(self.store,Silent(),{'boot_id':'reboot-without-sensor','reporting_commissioning':True,'ready':True,'sensor_extensions':True},now)
        self.assertFalse(self.job()['core_verified'])
        drive_commissioning(self.store,Silent(),{'boot_id':'reboot-without-sensor','reporting_commissioning':True,'ready':True,'sensor_extensions':True},now+301)
        self.assertEqual(self.job()['state'],'expired')
    def test_actuator_with_temperature_keeps_state_measurement(self):
        self.poller.once();ieee=self.sim.devices[0]['ieee']
        with self.store.lock,self.store.db:
            d=self.store._get(ieee);d['endpoints']['1']['input_clusters'].append(1026);self.store._put(d)
        view=next(d for d in self.store.device_views()['devices'] if d['ieee']==ieee)
        self.assertTrue(any(m['cluster']==6 for m in view['measurements']))
        self.assertTrue(self.dashboard.request('/api/v1/commands',{'op':'on_off','ieee':ieee,'endpoint':1,'state':True})['accepted'])
    def test_ul_on_off_protocol_report_is_not_measurement_history(self):
        self.add();self.sim.attr(2,6,16,1);self.poller.once()
        self.assertFalse(self.store.db.execute('SELECT 1 FROM measurements WHERE ieee=? AND cluster=6',(IEEE,)).fetchone())
    def test_gateway_command_validation_and_display_timeout_expiry(self):
        for command in ({'op':'write_display','ieee':IEEE,'endpoint':1,'request_id':'a'*36,'cluster':64529,'attribute':7,'value':2},
                        {'op':'sync_clock','unix_time':1,'utc_offset':0}):
            with self.assertRaises(ValueError):validate_command(command)
        self.add();now=time.time();self.store.start_display({'ieee':IEEE,'endpoint':1,'settings':{'temperature_units':'celsius'}},now)
        class Silent:
            def request(self,*a):return {'accepted':True}
        drive_display(self.store,Silent(),{'sensor_extensions':True,'ready':True},now)
        rid=self.display()['request_id'];self.assertTrue(rid)
        drive_display(self.store,Silent(),{'sensor_extensions':True,'ready':True},now+28);self.assertEqual(self.display()['state'],'waiting')
        drive_display(self.store,Silent(),{'sensor_extensions':True,'ready':True},now+301);self.assertEqual(self.display()['state'],'expired')
