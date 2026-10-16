"""All layout validation, legacy requests and isolated profile persistence."""
import copy
import json
import tempfile
import unittest
from sbc.core import Store
from sbc.dashboard import DashboardError
from sbc.all_layout import default_all_layout
from sbc.simulator import Simulation
from sbc.contracts_v2 import contract_v2
from jsonschema import Draft202012Validator


class AllLayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=self.tmp.name+'/all-layout.sqlite3';self.store=Store(self.path)
        self.addCleanup(lambda:self.store.close())
        self.sim=Simulation();self.sim.add_snzb02ul()
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)

    def body(self,profile='admin'):
        c=self.store.configuration_document(profile)
        return {k:copy.deepcopy(c[k]) for k in ('locations','devices','dashboard')}

    def save(self,layout,profile='admin'):
        body=self.body(profile);body['dashboard']['all_layout']=layout
        return self.store.replace_configuration(body,self.store.configuration_etag(profile),profile)

    def test_legacy_projection_no_rewrite_and_omitted_field_preserved(self):
        row=self.store.db.execute('select data,revision from dashboard_config').fetchone()
        self.assertNotIn('all_layout',json.loads(row[0]))
        self.assertEqual(self.store.configuration_document()['dashboard']['all_layout'],default_all_layout())
        self.assertEqual(self.store.db.execute('select data,revision from dashboard_config').fetchone(),row)
        layout=dict(columns=2,min_tile_width=300,order=[self.sim.devices[2]['ieee']])
        self.save(layout)
        body=self.body();body['dashboard'].pop('all_layout');body['dashboard']['title']='Legacy title update'
        result=self.store.replace_configuration(body,self.store.configuration_etag())
        self.assertEqual(result['dashboard']['all_layout'],layout)
        self.assertEqual(result['dashboard']['title'],'Legacy title update')

    def test_independent_profiles_restart_and_widget_preservation(self):
        admin=self.store.configuration_document();other=self.store.save_profile({'name':'Tablet'})['id']
        layout=dict(columns=4,min_tile_width=240,order=[self.sim.devices[2]['ieee'],self.sim.devices[1]['ieee']])
        self.save(layout,other)
        self.assertEqual(self.store.configuration_document(),admin)
        self.assertEqual(self.store.configuration_document(other)['dashboard']['widgets'],[])
        self.store.close();self.store=Store(self.path)
        self.assertEqual(self.store.configuration_document(other)['dashboard']['all_layout'],layout)
        self.assertEqual(self.store.configuration_document()['dashboard']['widgets'],admin['dashboard']['widgets'])

    def test_invalid_inputs_are_atomic_and_conflicts_rejected(self):
        original=self.store.configuration_document();base=default_all_layout()
        invalid=[None,{},dict(base,extra=True)]
        for v in (True,-1,7,2.5,'2'):invalid.append(dict(base,columns=v))
        for v in (True,180,660,250,240.5,'240'):invalid.append(dict(base,min_tile_width=v))
        for v in (None,'bad',[True],['bad'],['a'*16]*2,['a'*16]*51):invalid.append(dict(base,order=v))
        for v in invalid:
            with self.subTest(value=v):
                with self.assertRaises(DashboardError):self.save(v)
                self.assertEqual(self.store.configuration_document(),original)
        stale=self.store.configuration_etag();body=self.body();self.save(dict(base,columns=1))
        with self.assertRaises(DashboardError) as caught:self.store.replace_configuration(body,stale)
        self.assertEqual(caught.exception.status,412)

    def test_absent_addresses_retained_and_new_devices_not_reordered(self):
        missing='0000000000000001';sensor=self.sim.devices[1]['ieee']
        layout=dict(columns=0,min_tile_width=640,order=[missing,sensor])
        self.save(layout)
        self.sim.measure();self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.assertEqual(self.store.configuration_document()['dashboard']['all_layout'],layout)
        self.assertNotIn(missing,[d['ieee'] for d in self.store.snapshot()])
        for columns in range(7):
            for width in (200,240,640):self.save(dict(layout,columns=columns,min_tile_width=width))

    def test_contracts_accept_new_and_legacy_layouts(self):
        doc=contract_v2()
        validator=Draft202012Validator(dict(doc['components']['schemas']['ConfigurationInput'],components=doc['components']))
        body=self.body();validator.validate(body)
        body['dashboard'].pop('all_layout');validator.validate(body)
        body['dashboard']['all_layout']=dict(columns=7,min_tile_width=240,order=[])
        self.assertTrue(list(validator.iter_errors(body)))
