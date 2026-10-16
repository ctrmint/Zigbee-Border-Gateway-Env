"""Passive RSSI display, signal widgets and tablet layouts using synthetic events."""
import copy
import json
import time
from playwright.sync_api import expect
import browser_locations as base


class SignalBrowserTests(base.BrowserLocationTests):
    test_location_workflow_and_mobile_layout=None
    test_logout_during_pending_refresh=None

    def setUp(self):
        super().setUp()
        self.ieee=self.sim.devices[1]['ieee']
        self.room=self.store.save_location('Garage')
        self.store.assign_location(self.ieee,self.room['id'])
        self.sent=[];self.page.on('request',lambda r:self.sent.append((r.method,r.url)))

    def test_all_signal_is_read_only_and_fits_tablets(self):
        self.connect();self.page.get_by_role('tab',name='All',exact=True).click()
        tile=self.page.locator('[data-sensor-id="'+self.ieee+'"]')
        expect(tile.locator('.sensor-signal')).to_contain_text('-50 dBm')
        for width,height in ((390,844),(507,768),(768,1024),(1024,768),(1180,820)):
            self.page.set_viewport_size(dict(width=width,height=height))
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            expect(tile.locator('.sensor-signal')).to_be_visible()
        self.assertEqual(self.page.locator('#all-panel button,#all-panel input,#all-panel select,#all-panel summary').count(),0)
        self.assertFalse(any('/commands' in url or '/history' in url for _,url in self.sent))
        self.assertEqual(self.errors,[])

    def test_location_chart_numeric_and_setup_signal(self):
        c=self.store.configuration_document();body={k:copy.deepcopy(c[k]) for k in ('locations','devices','dashboard')}
        body['dashboard']['widgets']=[dict(id='signal-'+kind,type=kind,title='Signal '+kind,position=i,time_range=3600,
            source=dict(ieee=self.ieee,endpoint=1,cluster=65535,attribute=0)) for i,kind in enumerate(('chart','numeric'))]
        self.store.replace_configuration(body,self.store.configuration_etag())
        self.connect();self.page.get_by_role('tab',name='Garage',exact=True).click()
        expect(self.page.locator('#location-signals')).to_contain_text('-50 dBm')
        expect(self.page.locator('[data-widget-id="signal-numeric"] .reading')).to_contain_text('-50')
        expect(self.page.locator('[data-widget-id="signal-chart"] svg')).to_be_visible()
        expect(self.page.locator('[data-widget-id="signal-chart"]')).to_contain_text('dBm')
        self.page.get_by_role('button',name='Add widget',exact=True).click()
        expect(self.page.locator('#widget-source')).to_contain_text('Signal strength')
        self.page.get_by_role('button',name='Cancel',exact=True).click()
        self.page.get_by_role('tab',name='Configuration & Setup',exact=True).click()
        expect(self.page.locator('#devices .card').filter(has_text=self.ieee).locator('.sensor-signal')).to_contain_text('-50 dBm')
        self.assertFalse(any('/commands' in url for _,url in self.sent))
        self.assertEqual(self.errors,[])

    def test_stale_missing_and_old_latest_signal(self):
        row=self.store.db.execute('select data from signal_latest where ieee=?',(self.ieee,)).fetchone()
        d=json.loads(row[0]);d['received_at']=time.time()-7200
        with self.store.db:self.store.db.execute('update signal_latest set data=? where ieee=?',(json.dumps(d),self.ieee))
        self.connect();self.page.get_by_role('tab',name='All',exact=True).click()
        signal=self.page.locator('[data-sensor-id="'+self.ieee+'"] .sensor-signal')
        expect(signal).to_contain_text('-50 dBm');expect(signal).to_contain_text('Stale')
        with self.store.db:self.store.db.execute('delete from signal_latest where ieee=?',(self.ieee,))
        self.page.evaluate('refresh()');expect(signal).to_have_text('Signal: not received')
        self.assertEqual(self.errors,[])
