"""Optional browser checks: unittest discover -s tests -p browser_locations.py -v."""
import tempfile
import os
import threading
import unittest
import time
from http.server import ThreadingHTTPServer

from playwright.sync_api import expect, sync_playwright

from sbc.app import make_handler
from sbc.core import Poller, Store
from sbc.simulator import Simulation

TOKEN = 'b' * 64


class BrowserFixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name + '/browser.sqlite3')
        self.addCleanup(self.store.close)
        self.sim = Simulation()
        self.store.ingest(self.sim.boot, self.sim.events, self.sim.seq, self.sim.devices)
        poller = self.poller = Poller(None, self.store)
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
        browser_name = os.environ.get('DASHBOARD_TEST_BROWSER', 'chromium')
        if browser_name not in ('chromium', 'webkit'):
            raise ValueError('DASHBOARD_TEST_BROWSER must be chromium or webkit')
        self.browser = getattr(self.playwright, browser_name).launch(headless=True)
        self.addCleanup(self.browser.close)
        device = os.environ.get('DASHBOARD_TEST_DEVICE')
        self.page = self.browser.new_page(**(self.playwright.devices[device] if device else {}))
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
