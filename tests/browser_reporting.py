"""Optional Chromium commissioning controls and state transitions."""
import time
from playwright.sync_api import expect
import browser_locations as base
from sbc.commissioning import drive_commissioning

class ReportingBrowserTests(base.BrowserLocationTests):
    test_location_workflow_and_mobile_layout=None
    test_logout_during_pending_refresh=None
    def setUp(self):
        super().setUp()
        self.poller.status.update(reporting_commissioning=True)
    def test_configure_verify_cancel_retry_mobile_and_logout(self):
        self.connect()
        self.page.get_by_label('User-reported sensor model').select_option('SONOFF SNZB-02WD')
        self.page.get_by_role('button',name='Configure reporting',exact=True).click()
        expect(self.page.get_by_role('button',name='Cancel reporting setup')).to_be_visible()
        expect(self.page.locator('.reporting-status')).to_contain_text('queued')
        self.page.get_by_role('button',name='Cancel reporting setup').click()
        expect(self.page.locator('.reporting-status')).to_contain_text('cancelled')
        self.page.get_by_role('button',name='Retry / apply reporting settings',exact=True).click()
        # Drive genuine simulator operations and ingest the resulting acknowledgements.
        owner=self
        class Gateway:
            def request(self,path,body):return owner.sim.command(body)
        cursor=self.store.cursor()[1]
        for _ in range(10):
            drive_commissioning(self.store,Gateway(),dict(boot_id=self.sim.boot,reporting_commissioning=True))
            new=[e for e in self.sim.events if e['seq']>cursor]
            self.store.ingest(self.sim.boot,new,self.sim.seq);cursor=self.sim.seq
        expect(self.page.locator('.reporting-status')).to_contain_text('verified',timeout=10000)
        expect(self.page.get_by_text('Device acknowledged setup; observe unsolicited reports to prove delivery.',exact=True)).to_be_visible()
        expect(self.page.get_by_text('Model from device:',exact=False)).to_contain_text('SNZB-02WD')
        self.page.get_by_role('button',name='Use recommended freshness (4500s)',exact=True).click()
        self.wait_until("config.devices['00124b0000000002'].freshness_seconds === 4500")
        self.page.set_viewport_size({'width':360,'height':800})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        self.page.get_by_role('button',name='Disconnect',exact=True).click()
        expect(self.page.locator('#devices')).to_be_empty()
        self.assertEqual(self.errors,[])
    def test_old_gateway_controls_disabled(self):
        self.poller.status.pop('reporting_commissioning')
        self.connect()
        expect(self.page.get_by_role('button',name='Configure reporting',exact=True)).to_be_disabled()
        expect(self.page.get_by_text('Reporting setup requires connected gateway firmware with commissioning support.',exact=True)).to_be_visible()
