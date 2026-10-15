"""Optional end-to-end checks for location widgets and configuration conflicts."""
import json
import time
import threading
import unittest
from playwright.sync_api import expect
import browser_locations as base


class WidgetTests(base.BrowserLocationTests):
    def setUp(self):
        super().setUp()
        self.location=self.store.save_location('Garage')
        self.garden=self.store.save_location('Garden')
        self.sensor=self.sim.devices[1]['ieee']
        self.store.assign_location(self.sensor,self.location['id'])
        self.history_delay=threading.Event()

    def connect_location(self):
        self.connect()
        self.page.get_by_role('tab',name='Garage',exact=True).click()

    def suggestions(self):
        self.page.get_by_role('button',name='Add sensor widgets',exact=True).click()
        expect(self.page.locator('#widgets .widget')).to_have_count(4)
        expect(self.page.locator('#widgets svg')).to_have_count(2)

    def test_widgets_edit_reorder_range_and_reload(self):
        self.connect_location();self.suggestions()
        expect(self.page.locator('#widgets .reading').first).to_contain_text('20.5')
        self.page.locator('#widgets .widget').first.get_by_role('button',name='Edit',exact=True).click()
        self.page.get_by_label('Widget title',exact=True).fill('Room temperature')
        self.page.get_by_role('button',name='Save widget',exact=True).click()
        expect(self.page.get_by_role('heading',name='Room temperature',exact=True)).to_be_visible()
        self.page.get_by_role('button',name='Move Room temperature down',exact=True).click()
        self.wait_until("document.querySelector('#widgets .widget h3').textContent === 'Temperature history'")
        self.page.get_by_label('Time range for Temperature history',exact=True).select_option('604800')
        self.wait_until("config.dashboard.widgets.find(w=>w.type==='chart'&&w.source.cluster===1026).time_range===604800")
        self.page.reload();self.connect();self.page.get_by_role('tab',name='Garage',exact=True).click()
        expect(self.page.get_by_label('Time range for Temperature history')).to_have_value('604800')
        expect(self.page.get_by_role('heading',name='Room temperature',exact=True)).to_be_visible()
        chart=self.page.locator('#widgets svg').first
        chart.focus();chart.press('ArrowLeft')
        expect(self.page.locator('.chart-tooltip').first).to_contain_text('20.5')
        self.page.screenshot(path='/tmp/zigbee-dashboard-desktop.png',full_page=True)
        self.page.set_viewport_size({'width':360,'height':800})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        self.page.screenshot(path='/tmp/zigbee-dashboard-mobile.png',full_page=True)
        self.page.locator('#widgets .widget').last.get_by_role('button',name='Remove',exact=True).click()
        expect(self.page.locator('#widgets .widget')).to_have_count(3)
        self.assertEqual(self.errors,[])

    def test_endpoint_source_movement_empty_and_keyboard_tabs(self):
        self.sim.emit(dict(self.sim.devices[1],type='endpoint',endpoint=2,ok=True,profile_id=260,
            device_id=770,input_clusters=[1026],output_clusters=[]))
        self.sim.emit(dict(self.sim.devices[1],type='attribute',endpoint=2,cluster=1026,attribute=0,data_type=0x29,raw=1200,rssi=-50))
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.connect_location()
        self.page.get_by_role('button',name='Add widget',exact=True).click()
        options=self.page.get_by_label('Device endpoint measurement').locator('option')
        value=next(o.get_attribute('value') for o in options.all() if 'Endpoint 2' in o.inner_text())
        self.page.get_by_label('Device endpoint measurement').select_option(value)
        self.page.get_by_label('Widget title',exact=True).fill('Second endpoint')
        self.page.get_by_role('button',name='Save widget',exact=True).click()
        expect(self.page.locator('#widgets .reading')).to_contain_text('12')
        self.page.get_by_role('tab',name='Configuration & Setup').click()
        self.page.get_by_label('Location for '+self.sensor,exact=True).select_option(self.garden['id'])
        self.page.get_by_role('tab',name='Garden',exact=True).click()
        expect(self.page.get_by_role('heading',name='Second endpoint')).to_be_visible()
        self.page.get_by_role('tab',name='Garage',exact=True).click()
        expect(self.page.get_by_text('This space is ready for devices',exact=True)).to_be_visible()
        self.page.get_by_role('tab',name='Garage',exact=True).focus()
        self.page.keyboard.press('ArrowRight')
        expect(self.page.get_by_role('tab',name='Garden',exact=True)).to_be_focused()
        self.assertEqual(self.errors,[])

    def test_conflict_reapply_preserves_other_sessions_changes(self):
        self.connect_location();self.suggestions()
        self.page.locator('#widgets .widget').first.get_by_role('button',name='Edit',exact=True).click()
        self.page.get_by_label('Widget title',exact=True).fill('My pending title')
        current=self.store.configuration_document()
        draft={k:current[k] for k in ('locations','devices','dashboard')}
        draft['dashboard']['title']='Other session title'
        self.store.replace_configuration(draft,f'"configuration-{current["revision"]}"')
        self.page.get_by_role('button',name='Save widget',exact=True).click()
        expect(self.page.locator('#conflict')).to_be_visible()
        self.assertNotEqual(self.store.configuration_document()['dashboard']['widgets'][0]['title'],'My pending title')
        self.page.get_by_role('button',name='Reload & reapply edit',exact=True).click()
        expect(self.page.locator('#conflict')).to_be_hidden()
        expect(self.page.get_by_role('heading',name='My pending title',exact=True)).to_be_visible()
        self.assertEqual(self.store.configuration_document()['dashboard']['title'],'Other session title')
        self.assertEqual(self.errors,[])

    def test_reported_state_is_a_step_chart(self):
        self.store.assign_location(self.sim.devices[0]['ieee'],self.location['id'])
        self.sim.attr(0,6,0x10,1);self.sim.attr(0,6,0x10,0)
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.connect_location()
        self.page.get_by_role('button',name='Add widget',exact=True).click()
        options=self.page.get_by_label('Device endpoint measurement').locator('option')
        value=next(o.get_attribute('value') for o in options.all() if 'Reported state' in o.inner_text())
        self.page.get_by_label('Device endpoint measurement').select_option(value)
        self.page.get_by_label('Display',exact=True).select_option('chart')
        self.page.get_by_label('Widget title',exact=True).fill('Plug state')
        self.page.get_by_role('button',name='Save widget',exact=True).click()
        expect(self.page.locator('#widgets svg')).to_have_count(1)
        labels=self.page.locator('#widgets svg text').all_text_contents()
        self.assertIn('On',labels);self.assertIn('Off',labels)
        path=self.page.locator('#widgets svg path').get_attribute('d')
        self.assertIn('H',path);self.assertIn('V',path)
        self.assertEqual(self.errors,[])

    def test_offline_stale_invalid_gap_and_logout_during_history(self):
        d=self.store._get(self.sensor)
        d['attributes']['1:1026:0']['received']=time.time()-7200
        with self.store.db:
            self.store._put(d)
            self.store.db.execute('INSERT INTO ingestion_gaps(start,end,reason) VALUES(?,?,?)',(time.time()-50,time.time()-20,'test_gap'))
        self.connect_location();self.suggestions()
        expect(self.page.locator('.badge.stale').first).to_be_visible()
        expect(self.page.locator('.chart-gap').first).to_be_visible()
        self.sim.attr(1,1026,0x29,-32768);self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.page.evaluate('refresh()')
        expect(self.page.locator('.badge.invalid').first).to_be_visible()
        self.poller=None
        # HTTP polling continues to work while gateway status indicates an outage.
        self.page.route('**/api/v1/state',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps({'gateway':{'connected':False,'ready':False,'error':'offline','gap':False},'devices':self.store.snapshot(),'locations':self.store.locations()})))
        self.page.evaluate('refresh()')
        expect(self.page.locator('#status')).to_have_text('Gateway offline / starting')
        self.history_delay.set();self.waiting.clear();self.release.clear()
        self.page.get_by_label('Time range for Temperature history').select_option('604800')
        deadline=time.monotonic()+10
        while not self.waiting.is_set() and time.monotonic()<deadline:self.page.wait_for_timeout(50)
        self.assertTrue(self.waiting.is_set())
        self.page.get_by_role('button',name='Disconnect',exact=True).click()
        self.release.set()
        self.wait_until('requests.size===0')
        expect(self.page.locator('#widgets .widget')).to_have_count(0)
        expect(self.page.locator('#status')).to_have_text('Disconnected')
        self.assertEqual(self.errors,[])

    # These inherited tests have their own empty-location fixture.
    test_location_workflow_and_mobile_layout = None


if __name__=='__main__':unittest.main()
