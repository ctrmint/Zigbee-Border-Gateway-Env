"""Location-first navigation, separated setup tab and responsive keyboard access."""
import threading
from playwright.sync_api import expect
import browser_locations as base


class NavigationTests(base.BrowserLocationTests):
    test_location_workflow_and_mobile_layout = None
    test_logout_during_pending_refresh = None

    def setUp(self):
        super().setUp()
        self.alpha = self.store.save_location('Alpha')
        self.beta = self.store.save_location('Beta')
        self.gamma = self.store.save_location('Gamma')

    def tab(self, name):
        return self.page.get_by_role('tab', name=name, exact=True)

    def test_location_first_reconnect_reload_and_explicit_setup(self):
        expect(self.page.locator('#tabs')).to_be_hidden()
        expect(self.page.locator('#location-panel')).to_be_hidden()
        self.connect()
        expect(self.tab('Alpha')).to_have_attribute('aria-selected', 'true')
        expect(self.page.locator('#setup-panel')).to_be_hidden()
        expect(self.page.get_by_text('This space is ready for devices', exact=True)).to_be_visible()
        self.assertEqual(self.page.get_by_role('tab').all_text_contents(), ['Alpha', 'Beta', 'Gamma', 'Configuration & Setup'])
        self.tab('Configuration & Setup').click()
        self.page.evaluate('refresh()')
        self.store.save_location('Delta')
        self.page.evaluate('refresh()')
        expect(self.tab('Configuration & Setup')).to_have_attribute('aria-selected', 'true')
        expect(self.page.locator('#setup-panel')).to_be_visible()
        self.page.get_by_role('button', name='Disconnect', exact=True).click()
        expect(self.page.locator('#tabs')).to_be_empty()
        self.connect()
        expect(self.tab('Alpha')).to_have_attribute('aria-selected', 'true')
        self.tab('Gamma').click()
        self.page.reload(); self.connect()
        expect(self.tab('Alpha')).to_have_attribute('aria-selected', 'true')
        self.assertEqual(self.page.evaluate('localStorage.length + sessionStorage.length'), 0)
        self.assertEqual(self.errors, [])

    def test_rename_and_deleted_active_location_fallback(self):
        self.connect()
        expect(self.tab('Alpha')).to_have_attribute('aria-selected', 'true')
        self.store.save_location('Zulu', self.alpha['id'])
        self.page.evaluate('refresh()')
        expect(self.tab('Zulu')).to_have_attribute('aria-selected', 'true')
        expect(self.page.locator('#location-title')).to_have_text('Zulu')
        self.store.delete_location(self.alpha['id'])
        self.page.evaluate('refresh()')
        expect(self.tab('Beta')).to_have_attribute('aria-selected', 'true')
        self.store.delete_location(self.beta['id']); self.store.delete_location(self.gamma['id'])
        self.page.evaluate('refresh()')
        expect(self.tab('Configuration & Setup')).to_have_attribute('aria-selected', 'true')
        expect(self.page.locator('#setup-panel')).to_be_visible()
        self.assertEqual(self.page.get_by_role('tab').count(), 1)
        self.page.reload(); self.connect()
        expect(self.tab('Configuration & Setup')).to_have_attribute('aria-selected', 'true')
        self.assertEqual(self.errors, [])

    def test_alignment_overflow_keyboard_and_mobile(self):
        self.connect()
        expect(self.tab('Alpha')).to_be_visible()
        bounds=self.page.evaluate('''() => {
          const bar=document.querySelector('#tabs').getBoundingClientRect(),
            first=document.querySelector('#location-tabs button').getBoundingClientRect(),
            setup=document.querySelector('#tab-setup').getBoundingClientRect();
          return {barLeft:bar.left,barRight:bar.right,firstLeft:first.left,setupRight:setup.right};
        }''')
        self.assertAlmostEqual(bounds['barLeft'], bounds['firstLeft'], delta=4)
        self.assertAlmostEqual(bounds['barRight'], bounds['setupRight'], delta=1)
        self.tab('Alpha').focus(); self.page.keyboard.press('End')
        expect(self.tab('Configuration & Setup')).to_be_focused()
        self.page.keyboard.press('ArrowLeft'); expect(self.tab('Gamma')).to_be_focused()
        self.page.keyboard.press('Home'); expect(self.tab('Alpha')).to_be_focused()
        self.page.keyboard.press('ArrowLeft'); expect(self.tab('Configuration & Setup')).to_be_focused()
        self.page.keyboard.press('ArrowRight'); expect(self.tab('Alpha')).to_be_focused()
        for i in range(12): self.store.save_location(f'Long location {i:02d} '+ 'with a long room name '*2)
        self.page.evaluate('refresh()')
        for width in (1280, 360):
            self.page.set_viewport_size({'width':width,'height':800})
            self.tab('Alpha').focus(); self.page.keyboard.press('Home')
            names=self.page.get_by_role('tab').all_text_contents()
            for name in names[1:]:
                self.page.keyboard.press('ArrowRight')
                tab=self.tab(name)
                expect(tab).to_be_focused(); expect(tab).to_have_attribute('aria-selected','true')
                rect=tab.bounding_box(); setup=self.tab('Configuration & Setup').bounding_box()
                self.assertGreaterEqual(rect['x'],0)
                self.assertLessEqual(rect['x']+rect['width'],width+1)
                if name!='Configuration & Setup':self.assertLessEqual(rect['x'],setup['x'])
                self.assertLessEqual(setup['x']+setup['width'],width+1)
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
            self.assertEqual(self.page.locator('#tabs [tabindex="0"]').count(),1)
        self.assertEqual(self.errors, [])

    def test_active_location_change_cancels_pending_history_and_logout(self):
        sensor=self.sim.devices[1]['ieee']
        self.store.assign_location(sensor,self.alpha['id'])
        self.history_delay=threading.Event(); self.history_delay.set()
        self.connect()
        expect(self.tab('Alpha')).to_have_attribute('aria-selected','true')
        self.page.get_by_role('button',name='Add sensor widgets',exact=True).click()
        self.wait_until('chartRequests.size > 0')
        # Delete the selected tab while history requests are in flight.
        self.store.assign_location(sensor,self.beta['id']);self.store.delete_location(self.alpha['id'])
        self.page.evaluate('refresh()')
        expect(self.tab('Beta')).to_have_attribute('aria-selected','true')
        self.tab('Configuration & Setup').click()
        self.wait_until('chartRequests.size === 0')
        self.page.get_by_role('button',name='Disconnect',exact=True).click()
        self.release.set()
        self.wait_until('requests.size === 0')
        expect(self.page.locator('#widgets')).to_be_empty()
        expect(self.page.locator('#devices')).to_be_empty()
        expect(self.page.locator('#status')).to_have_text('Disconnected')
        self.assertEqual(self.errors, [])
