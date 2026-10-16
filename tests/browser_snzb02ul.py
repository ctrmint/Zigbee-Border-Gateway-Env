"""Optional synthetic UL setup/UI checks; the physical device is not connected."""
import json
from playwright.sync_api import expect
import browser_locations as base
from sbc.commissioning import drive_commissioning
from sbc.display import drive_display

class ULBrowserTests(base.BrowserLocationTests):
    test_location_workflow_and_mobile_layout=None
    test_logout_during_pending_refresh=None
    def setUp(self):
        super().setUp();self.poller.status.update(sensor_extensions=True,reporting_commissioning=True)
    def add(self,**kwargs):
        self.ul=self.sim.add_snzb02ul(**kwargs);self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.location=self.store.save_location('AirGuard');self.store.assign_location(self.ul['ieee'],self.location['id'])
    def setup_tab(self):self.page.get_by_role('tab',name='Configuration & Setup',exact=True).click()
    def drive(self,display=False):
        owner=self
        class Gateway:
            def request(self,path,body):return owner.sim.command(body)
        cursor=self.store.cursor()[1]
        for _ in range(18):
            (drive_display if display else drive_commissioning)(self.store,Gateway(),dict(boot_id=self.sim.boot,ready=True,sensor_extensions=True,reporting_commissioning=True))
            self.store.ingest(self.sim.boot,[e for e in self.sim.events if e['seq']>cursor],self.sim.seq);cursor=self.sim.seq
    def test_ul_defaults_battery_widgets_and_display_settings(self):
        self.add(voltage=False)
        with self.store.lock,self.store.db:self.store.db.execute('INSERT INTO device_settings(ieee,freshness_seconds) VALUES(?,?)',(self.ul['ieee'],1800))
        self.connect();self.setup_tab()
        card=self.page.locator('#devices .card').filter(has_text=self.ul['ieee'])
        expect(card.get_by_label('User-reported sensor model')).to_have_value('SONOFF SNZB-02UL')
        expect(card.get_by_label('Maximum report interval (seconds) for '+self.ul['ieee'],exact=True)).to_have_value('1800')
        expect(card.get_by_role('button',name='On · EP 1',exact=True)).to_have_count(0)
        expect(card.get_by_role('button',name='Read state · EP 1',exact=True)).to_have_count(0)
        self.assertIn('Battery',card.locator('.metrics').inner_text())
        self.assertNotIn('Battery voltage',card.locator('.metrics').inner_text())
        card.get_by_role('button',name='Configure reporting',exact=True).click();self.drive()
        expect(card.locator('.reporting-status')).to_contain_text('verified',timeout=10000)
        card.get_by_role('button',name='Use recommended freshness (2250s)',exact=True).click()
        self.wait_until("config.devices['00124b0000000014'].freshness_seconds===2250")
        card.get_by_text('SNZB-02UL E-Ink settings (hardware verification pending)',exact=True).click()
        card.get_by_label('Display setting for '+self.ul['ieee'],exact=True).select_option('comfort_temperature_min')
        card.get_by_label('Display setting value for '+self.ul['ieee'],exact=True).fill('19.5')
        card.get_by_role('button',name='Apply display setting',exact=True).click();self.drive(display=True)
        expect(card.locator('.display-status')).to_contain_text('verified',timeout=10000)
        self.page.get_by_role('tab',name='AirGuard',exact=True).click()
        self.page.get_by_role('button',name='Add sensor widgets',exact=True).click()
        expect(self.page.locator('#widgets .widget')).to_have_count(6)
        expect(self.page.get_by_role('heading',name='Battery',exact=True)).to_be_visible()
        self.page.reload();self.connect();expect(self.page.locator('#widgets .widget')).to_have_count(6)
        self.page.set_viewport_size({'width':360,'height':800})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.page.get_by_role('button',name='Disconnect',exact=True).click()
        expect(self.page.locator('#devices')).to_be_empty();expect(self.page.locator('#widgets')).to_be_empty()
        self.assertEqual(self.errors,[])
    def test_unconnected_profile_and_old_gateway_controls(self):
        self.poller.status.pop('sensor_extensions');self.connect()
        self.page.get_by_text('Prepared sensor support',exact=True).click()
        expect(self.page.locator('#profile-list')).to_contain_text('SONOFF SNZB-02UL · Prepared in software; physical validation pending')
        expect(self.page.locator('#devices .card')).to_have_count(2)
        self.page.get_by_label('User-reported sensor model').select_option('SONOFF SNZB-02UL')
        expect(self.page.get_by_label('Maximum report interval (seconds) for '+self.sim.devices[1]['ieee'],exact=True)).to_have_value('1800')
        expect(self.page.get_by_role('button',name='Configure reporting',exact=True)).to_be_disabled()
        self.assertEqual(self.errors,[])
    def test_missing_vendor_optional_and_low_battery_stale(self):
        self.add(vendor_cluster=False);self.sim.attr(2,1,32,20,33)
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.connect();self.setup_tab();card=self.page.locator('#devices .card').filter(has_text=self.ul['ieee'])
        expect(card.locator('.metrics')).to_contain_text('Low battery')
        card.get_by_text('SNZB-02UL E-Ink settings (hardware verification pending)',exact=True).click()
        expect(card.get_by_text('Vendor settings are unavailable on this discovered endpoint. Core sensor readings still work.',exact=True)).to_be_visible()
        expect(card.get_by_role('button',name='Apply display setting',exact=True)).to_have_count(0)
        self.page.get_by_role('tab',name='AirGuard',exact=True).click()
        self.page.get_by_role('button',name='Add sensor widgets',exact=True).click()
        expect(self.page.locator('#widgets .badge').filter(has_text='Low battery').first).to_be_visible()
        self.assertEqual(self.errors,[])
