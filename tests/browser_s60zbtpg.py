"""Synthetic plug UI; physical iPad/plug acceptance is separate."""
import time
from playwright.sync_api import expect
import browser_locations as base
from sbc.plug_jobs import drive_plugs

class PlugBrowserTests(base.BrowserLocationTests):
    test_location_workflow_and_mobile_layout=None
    test_logout_during_pending_refresh=None
    def setUp(self):
        super().setUp();self.sim.add_s60zbtpg();self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.location=self.store.save_location('Plug bench')['id'];self.store.assign_location('00124b0000000027',self.location)
        self.poller.status.update(plug_extensions=True,boot_id=self.sim.boot)
    def drive(self,n=80):
        owner=self
        class Gateway:
            def request(self,path,body):return owner.sim.command(body)
        for i in range(n):
            drive_plugs(self.store,Gateway(),self.poller.status,time.time()+4+i*4)
            seq=self.store.cursor()[1];self.store.ingest(self.sim.boot,[e for e in self.sim.events if e['seq']>seq],self.sim.seq,self.sim.devices)
            if self.store.plug_document()['jobs'][0]['state'] not in ('queued','waiting','sending'):break
        self.page.evaluate('refresh()')
    def test_readonly_all_telemetry_and_responsive_layout(self):
        methods=[];self.page.on('request',lambda r:methods.append(r.method));self.connect();self.page.get_by_role('tab',name='All',exact=True).click()
        tile=self.page.locator('[data-sensor-id="00124b0000000027"]');expect(tile).to_be_visible()
        expect(tile).to_contain_text('Reported state');expect(tile).to_contain_text('Active power');expect(tile).to_contain_text('Accumulated energy');expect(tile).to_contain_text('On');expect(tile.locator('button,input,select')).to_have_count(0)
        self.assertNotIn('Temperature',tile.inner_text());self.assertNotIn('Battery',tile.inner_text());self.assertTrue(all(m=='GET' for m in methods))
        for width in (1180,768,390):
            self.page.set_viewport_size({'width':width,'height':900});self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.assertEqual(self.errors,[])
    def test_settings_jobs_relay_readback_and_location_controls(self):
        self.connect();self.page.get_by_role('tab',name='Configuration & Setup',exact=True).click();self.page.get_by_text('S60ZBTPG controls (physical verification pending)',exact=True).click()
        self.page.get_by_role('button',name='Request Off',exact=True).click();expect(self.page.locator('#devices .plug-status')).to_contain_text('queued')
        self.assertTrue(self.store._get('00124b0000000027')['attributes']['1:6:0']['value']);self.drive();expect(self.page.locator('#devices .plug-status')).to_contain_text('verified')
        self.page.get_by_text('S60ZBTPG controls (physical verification pending)',exact=True).click()
        self.page.get_by_label('Power-loss behavior',exact=True).select_option('previous');self.page.get_by_role('button',name='Apply power-loss behavior',exact=True).click();self.drive();expect(self.page.locator('#devices .plug-status')).to_contain_text('verified')
        self.page.get_by_text('S60ZBTPG controls (physical verification pending)',exact=True).click()
        self.page.get_by_label('Maximum current (A)',exact=True).fill('10');self.page.get_by_label('Maximum power (W)',exact=True).fill('2000');self.page.get_by_role('button',name='Apply protection thresholds',exact=True).click();self.drive();expect(self.page.locator('#devices .plug-status')).to_contain_text('verified')
        self.page.get_by_role('tab',name='Plug bench',exact=True).click();expect(self.page.get_by_role('button',name='Request On',exact=True)).to_be_visible();self.page.evaluate("window.plugButtonBefore=document.querySelector('#location-plugs [data-plug-state=on]')");self.page.evaluate('refresh()');self.page.wait_for_timeout(300);self.assertTrue(self.page.evaluate("window.plugButtonBefore===document.querySelector('#location-plugs [data-plug-state=on]')"));self.page.get_by_role('button',name='Request On',exact=True).click();self.drive();expect(self.page.locator('#location-plugs .plug-status')).to_contain_text('verified')
        self.page.get_by_role('tab',name='All',exact=True).click();expect(self.page.locator('[data-sensor-id="00124b0000000027"]')).to_contain_text('On');self.page.get_by_role('button',name='Disconnect',exact=True).click();expect(self.page.locator('#location-plugs')).to_be_empty();self.assertEqual(self.errors,[])

    def test_metering_widgets_and_chart_history(self):
        doc=self.store.configuration_document();body={k:doc[k] for k in ('locations','devices','dashboard')}
        body['dashboard']['widgets']=[dict(id='plug-power',type='chart',title='Power history',position=0,time_range=3600,source=dict(ieee='00124b0000000027',endpoint=1,cluster=64529,attribute=0x7006)),dict(id='plug-energy',type='numeric',title='Energy total',position=1,time_range=3600,source=dict(ieee='00124b0000000027',endpoint=1,cluster=1794,attribute=0)),dict(id='plug-state',type='numeric',title='Relay state',position=2,time_range=3600,source=dict(ieee='00124b0000000027',endpoint=1,cluster=6,attribute=0))]
        self.store.replace_configuration(body,self.store.configuration_etag());methods=[];self.page.on('request',lambda r:methods.append(r.method));self.connect();self.page.get_by_role('tab',name='Plug bench',exact=True).click()
        expect(self.page.locator('#widgets svg[role=img]')).to_have_count(1);expect(self.page.locator('#widgets')).to_contain_text('123,456,789.012');expect(self.page.locator('#widgets')).to_contain_text('On')
        self.assertTrue(all(m=='GET' for m in methods));self.assertEqual(self.errors,[])
