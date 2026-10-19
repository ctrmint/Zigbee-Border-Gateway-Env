"""Preview layout migration/preservation, bounds, isolation and atomic conflicts."""
import copy
import unittest
import test_all_layout as base
from sbc.dashboard import DashboardError
from sbc.grid_layout import default_grid_layout
from sbc.contracts_v2 import contract_v2
from jsonschema import Draft202012Validator


class GridLayoutTests(base.AllLayoutTests):
    # Reuse the fixture only; keep inherited legacy assertions in their original suite.
    test_legacy_projection_no_rewrite_and_omitted_field_preserved = None
    test_independent_profiles_restart_and_widget_preservation = None
    test_invalid_inputs_are_atomic_and_conflicts_rejected = None
    test_absent_addresses_retained_and_new_devices_not_reordered = None
    test_contracts_accept_new_and_legacy_layouts = None

    def save_grid(self, layout, profile='admin'):
        body=self.body(profile);body['dashboard']['grid_layout']=layout
        return self.store.replace_configuration(body,self.store.configuration_etag(profile),profile)

    def test_no_rewrite_legacy_writes_and_profile_restart(self):
        before=self.store.db.execute('select data,revision from dashboard_config').fetchone()
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout'],default_grid_layout())
        self.assertEqual(before,self.store.db.execute('select data,revision from dashboard_config').fetchone())
        layout=default_grid_layout();layout['theme']='dark'
        layout['all']['desktop']=[dict(id='a'*16,x=0,y=0,w=4,h=4)]
        other=self.store.save_profile({'name':'Preview tablet'})['id'];admin=self.body()
        self.save_grid(layout,other)
        legacy=self.body(other);legacy['dashboard'].pop('grid_layout');legacy['dashboard']['title']='Older browser'
        self.store.replace_configuration(legacy,self.store.configuration_etag(other),other)
        self.assertEqual(self.store.configuration_document(other)['dashboard']['grid_layout'],layout)
        self.assertEqual(self.body(),admin)
        self.store.close()
        from sbc.core import Store
        self.store=Store(self.path)
        self.assertEqual(self.store.configuration_document(other)['dashboard']['grid_layout'],layout)

    def test_geometry_rejection_atomicity_and_stale_revision(self):
        original=self.store.configuration_document();layout=default_grid_layout()
        bad=[None,{},dict(layout,version=True),dict(layout,version=2),dict(layout,theme='purple')]
        rect=dict(id='a'*16,x=0,y=0,w=4,h=4)
        for patch in ({'x':True},{'x':12},{'w':13},{'y':1001},{'h':2},{'id':'<html>'},{'h':21},{'y':0.5},{'content':'bad'}):
            candidate=copy.deepcopy(layout);candidate['all']['desktop']=[dict(rect,**patch)];bad.append(candidate)
        candidate=copy.deepcopy(layout);candidate['all']['tablet']=[rect,dict(rect,id='b'*16,x=3)];bad.append(candidate)
        candidate=copy.deepcopy(layout);candidate['all']['mobile']=[rect];bad.append(candidate)
        for value in bad:
            with self.subTest(value=value):
                with self.assertRaises(DashboardError):self.save_grid(value)
                self.assertEqual(self.store.configuration_document(),original)
        self.save_grid(layout);body=self.body()
        with self.assertRaises(DashboardError) as e:self.store.replace_configuration(body,'"configuration-1"')
        self.assertEqual(e.exception.status,412)

    def test_contract_and_absent_geometry_preserved(self):
        layout=default_grid_layout();layout['all']['desktop']=[dict(id='0'*16,x=0,y=2,w=4,h=6)]
        result=self.save_grid(layout);self.assertEqual(result['dashboard']['grid_layout'],layout)
        doc=contract_v2();validator=Draft202012Validator(dict(doc['components']['schemas']['Configuration'],components=doc['components']))
        validator.validate(result)
        self.sim.measure();self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout'],layout)

    def test_location_layout_isolation_legacy_preservation_and_bounds(self):
        layout=default_grid_layout();layout['locations']={'room':{'desktop':[dict(id='reading-1',x=0,y=0,w=6,h=4)],'tablet':[],'mobile':[]}}
        other=self.store.save_profile({'name':'Layout profile'})['id']
        self.save_grid(layout,other)
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout']['locations'],{})
        older=copy.deepcopy(layout);older.pop('locations');older['theme']='dark'
        result=self.save_grid(older,other)['dashboard']['grid_layout']
        self.assertEqual(result['locations'],layout['locations'])
        bad=copy.deepcopy(result);bad['locations']['room']['desktop'].append(dict(id='reading-2',x=5,y=0,w=6,h=4))
        with self.assertRaises(DashboardError):self.save_grid(bad,other)
        self.assertEqual(self.store.configuration_document(other)['dashboard']['grid_layout'],result)
        doc=contract_v2();Draft202012Validator(dict(doc['components']['schemas']['Configuration'],components=doc['components'])).validate(self.store.configuration_document(other))

    def test_presentation_persistence_isolation_omission_and_restart(self):
        layout=default_grid_layout();layout['presentation']={'version':1,'defaults':{'size':52,'font':'mono'},'all':{'a'*16:{'scale':125,'color':'#38cdec','trend':False}},'widgets':{'reading-1':{'size':72}}}
        other=self.store.save_profile({'name':'Typography'})['id']
        self.save_grid(layout,other)
        self.assertNotIn('presentation',self.body()['dashboard']['grid_layout'])
        older=copy.deepcopy(layout);older.pop('presentation');older['theme']='dark'
        self.save_grid(older,other)
        self.assertEqual(self.body(other)['dashboard']['grid_layout']['presentation'],layout['presentation'])
        self.store.close()
        from sbc.core import Store
        self.store=Store(self.path)
        self.assertEqual(self.body(other)['dashboard']['grid_layout']['presentation'],layout['presentation'])
        doc=contract_v2();Draft202012Validator(dict(doc['components']['schemas']['Configuration'],components=doc['components'])).validate(self.store.configuration_document(other))

    def test_invalid_presentation_is_atomic_and_conflict_safe(self):
        original=self.store.configuration_document()
        valid={'version':1,'defaults':{},'all':{},'widgets':{}}
        invalid=[None,{},dict(valid,version=True),dict(valid,version=2),dict(valid,all={'invalid':{}})]
        for patch in ({'size':23},{'size':97},{'size':True},{'scale':74},{'scale':151},{'scale':float('nan')},{'font':'remote-url'},{'color':'red'},{'color':'#fff'},{'color':'url(https://example.com)'},{'trend':1},{'unexpected':1}):
            invalid.append(dict(valid,defaults=patch))
        for presentation in invalid:
            with self.subTest(presentation=presentation):
                layout=default_grid_layout();layout['presentation']=presentation
                with self.assertRaises(DashboardError):self.save_grid(layout)
                self.assertEqual(self.store.configuration_document(),original)
        layout=default_grid_layout();layout['presentation']=dict(valid,defaults={'size':96,'scale':150,'font':'serif','color':'#FFFFFF'})
        self.save_grid(layout)
        with self.assertRaises(DashboardError) as e:self.store.replace_configuration(self.body(),'"configuration-1"')
        self.assertEqual(e.exception.status,412)
