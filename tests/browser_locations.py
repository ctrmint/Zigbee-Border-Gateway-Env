"""Optional browser checks: unittest discover -s tests -p browser_locations.py -v."""
import tempfile
import threading
import unittest
import time
from http.server import ThreadingHTTPServer

from playwright.sync_api import expect, sync_playwright

from sbc.app import make_handler
from sbc.core import Poller, Store
from sbc.simulator import Simulation

TOKEN = 'b' * 64


class BrowserLocationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name + '/browser.sqlite3')
        self.addCleanup(self.store.close)
        self.sim = Simulation()
        self.store.ingest(self.sim.boot, self.sim.events, self.sim.seq, self.sim.devices)
        poller = Poller(None, self.store)
        poller.status = dict(connected=True, ready=True, gap=False, mode='simulator')
        self.delay = threading.Event(); self.waiting = threading.Event(); self.release = threading.Event()
        handler = make_handler(self.store, poller, None, TOKEN)
        owner = self
        class DelayedHandler(handler):
            def do_GET(inner):
                if inner.path == '/api/v1/state' and owner.delay.is_set():
                    owner.waiting.set(); owner.release.wait(10)
                if inner.path.startswith('/api/v2/history?') and getattr(owner, 'history_delay', None) and owner.history_delay.is_set():
                    owner.waiting.set(); owner.release.wait(10)
                try:
                    super().do_GET()
                except (BrokenPipeError, ConnectionResetError):
                    pass  # A logged-out browser deliberately aborts pending requests.
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), DelayedHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.release.set)
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch(headless=True)
        self.addCleanup(self.browser.close)
        self.page = self.browser.new_page()
        self.errors = []
        self.page.on('pageerror', lambda error: self.errors.append(str(error)))
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}')

    def connect(self):
        self.page.get_by_label('Dashboard access token').fill(TOKEN)
        self.page.get_by_role('button', name='Connect', exact=True).click()

    def wait_until(self, expression):
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            if self.page.evaluate(expression): return
            self.page.wait_for_timeout(50)
        self.fail('Browser condition did not become true: '+expression)

    def test_location_workflow_and_mobile_layout(self):
        self.connect()
        expect(self.page.locator('#devices .card')).to_have_count(2)
        self.page.get_by_label('New location').fill('Kitchen')
        self.page.get_by_role('button', name='Add location', exact=True).click()
        expect(self.page.get_by_label('Rename Kitchen')).to_be_visible()
        location = self.store.locations()[0]
        for device in self.sim.devices:
            self.page.get_by_label('Location for ' + device['ieee'], exact=True).select_option(location['id'])
        expect(self.page.get_by_role('tab', name='Kitchen', exact=True)).to_be_visible()
        self.wait_until("document.querySelector('#location-list').textContent.includes('2 devices')")
        expect(self.page.get_by_role('button', name='Delete', exact=True)).to_be_disabled()
        self.page.get_by_label('Rename Kitchen').fill('Greenhouse')
        self.page.get_by_role('button', name='Save name', exact=True).click()
        expect(self.page.get_by_role('tab', name='Greenhouse', exact=True)).to_be_visible()
        for device in self.sim.devices:
            self.page.get_by_label('Location for ' + device['ieee'], exact=True).select_option('')
        self.wait_until("document.querySelector('#location-list').textContent.includes('0 devices')")
        self.page.get_by_role('button', name='Delete', exact=True).click()
        expect(self.page.locator('#location-list .location-row')).to_have_count(0, timeout=10000)
        self.page.set_viewport_size({'width': 360, 'height': 800})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
        self.assertEqual(self.store.locations(), [])
        self.assertEqual(self.errors, [])

    def test_logout_during_pending_refresh(self):
        self.delay.set(); self.connect()
        self.assertTrue(self.waiting.wait(5))
        self.page.get_by_role('button', name='Disconnect', exact=True).click()
        self.release.set()
        self.wait_until('requests.size === 0')
        expect(self.page.locator('#devices .card')).to_have_count(0)
        expect(self.page.locator('#locations-panel')).to_be_hidden()
        expect(self.page.locator('#status')).to_have_text('Disconnected')
        self.assertEqual(self.errors, [])


if __name__ == '__main__':
    unittest.main()
