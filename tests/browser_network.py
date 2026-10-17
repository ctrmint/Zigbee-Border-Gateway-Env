"""Network diagnostics distinguish local recovery state from Zigbee readings."""
from playwright.sync_api import expect
import browser_locations as base

class NetworkBrowserTests(base.BrowserLocationTests):
    test_location_workflow_and_mobile_layout=None
    test_logout_during_pending_refresh=None
    def test_network_diagnostics_and_offline_recovery(self):
        self.poller.status.update(gateway_id='b8f86262ff08',network=dict(associated=True,ip_ready=True,api_ok=True,attempts=9,last_disconnect_reason=201,ipv4='10.81.1.42'))
        self.connect();self.page.get_by_role('tab',name='Configuration & Setup',exact=True).click()
        self.page.get_by_text('Wi-Fi recovery diagnostics',exact=True).click()
        expect(self.page.locator('#network-diagnostics')).to_contain_text('"attempts": 9')
        self.poller.status.update(connected=False,error='URLError')
        self.page.evaluate('refresh()');expect(self.page.locator('#gateway-state')).to_have_text('Offline / starting');expect(self.page.locator('#network-diagnostics')).to_contain_text('Cached data; gateway offline')
        self.poller.status.update(connected=True,error=None)
        self.page.evaluate('refresh()');expect(self.page.locator('#gateway-state')).to_have_text('Connected')
        self.page.get_by_role('button',name='Disconnect',exact=True).click()
        expect(self.page.locator('#network-diagnostics')).to_have_text('Disconnected.')
        self.assertEqual(self.errors,[])
