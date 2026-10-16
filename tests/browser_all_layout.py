"""Per-profile All layout controls, responsive fallback and stable sensor placement."""
import copy
from playwright.sync_api import expect
import browser_all as base


class AllLayoutBrowserTests(base.AllTests):
    test_read_only_capabilities_and_no_extra_requests=None
    test_mixed_endpoints_unassigned_and_battery_states=None
    test_updates_stale_offline_missing_and_stable_nodes=None
    test_dense_tablet_layout_long_names_zoom_and_scroll=None
    test_empty_and_preserve_default_navigation=None

    def setUp(self):
        super().setUp();self.sim.add_snzb02ul();self.update()

    def setup_layout(self):self.page.get_by_role('tab',name='Configuration & Setup',exact=True).click()
    def save_layout(self,columns,width):
        self.setup_layout();self.page.get_by_label('Tiles across',exact=True).select_option(str(columns))
        self.page.get_by_label('Minimum tile width (pixels)',exact=True).fill(str(width))
        self.page.get_by_role('button',name='Save All layout',exact=True).click()
        expect(self.page.locator('#notice')).to_have_text('Dashboard saved.')

    def test_counts_widths_rotation_and_read_only_tiles(self):
        self.open_all();self.save_layout(2,240)
        self.page.get_by_role('tab',name='All',exact=True).click()
        expect(self.page.locator('#all-grid')).to_have_attribute('data-columns','2')
        before=len(self.sent)
        for width,height,count in ((390,844,'1'),(768,1024,'2'),(1024,768,'2'),(507,768,'1')):
            self.page.set_viewport_size(dict(width=width,height=height))
            expect(self.page.locator('#all-grid')).to_have_attribute('data-columns',count)
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        expect(self.page.locator('#all-layout-status')).to_contain_text('1 of 2 requested columns fit')
        self.assertFalse(any('/commands' in u or '/history' in u for _,u in self.sent[before:]))
        self.assertEqual(self.page.locator('#all-panel button,#all-panel input,#all-panel select,#all-panel summary').count(),0)
        self.page.set_viewport_size(dict(width=1180,height=820));self.save_layout(1,240)
        self.page.get_by_role('tab',name='All',exact=True).click();expect(self.page.locator('#all-grid')).to_have_attribute('data-columns','1')
        self.page.reload();self.connect();self.page.get_by_role('tab',name='All',exact=True).click()
        expect(self.page.locator('#all-grid')).to_have_attribute('data-columns','1');self.assertEqual(self.errors,[])

    def test_sensor_order_new_departed_and_returning(self):
        self.open_all();ids=self.page.locator('.sensor-tile').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.sensorId)')
        self.setup_layout();self.page.locator('#all-tile-order li').nth(1).get_by_role('button').first.click()
        self.page.get_by_role('button',name='Save All layout',exact=True).click();expect(self.page.locator('#notice')).to_have_text('Dashboard saved.')
        self.page.get_by_role('tab',name='All',exact=True).click()
        expected=list(reversed(ids));self.assertEqual(self.page.locator('.sensor-tile').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.sensorId)'),expected)
        # New unranked sensors are appended, even if their address sorts first.
        new={'ieee':'0000000000000001','nwk':123,'active':True};self.sim.devices.append(new)
        self.sim.emit(dict(new,type='announce'));self.sim.emit(dict(new,type='endpoint',endpoint=1,ok=True,profile_id=260,device_id=770,input_clusters=[1026],output_clusters=[]));self.update()
        expect(self.page.locator('.sensor-tile')).to_have_count(3)
        self.assertEqual(self.page.locator('.sensor-tile').last.get_attribute('data-sensor-id'),new['ieee'])
        self.sim.devices[1]['active']=False;self.update();expect(self.page.locator('.sensor-tile')).to_have_count(2)
        self.sim.devices[1]['active']=True;self.update();expect(self.page.locator('.sensor-tile')).to_have_count(3)
        self.assertEqual(self.page.locator('.sensor-tile').evaluate_all('(nodes)=>nodes.map(n=>n.dataset.sensorId)'),expected+[new['ieee']])
        self.assertEqual(self.errors,[])

    def test_profile_isolation_discard_and_width_precedence(self):
        self.page.set_viewport_size(dict(width=1180,height=820))
        other=self.store.save_profile({'name':'Tablet'})['id'];self.open_all();self.save_layout(4,360)
        self.page.get_by_role('tab',name='All',exact=True).click()
        expect(self.page.locator('#all-grid')).to_have_attribute('data-columns','3')
        self.page.get_by_label('Active user profile',exact=True).select_option(other)
        expect(self.page.locator('#all-layout-status')).to_contain_text('Auto layout')
        self.save_layout(1,240);self.setup_layout()
        self.page.get_by_label('Tiles across',exact=True).select_option('6')
        self.page.get_by_role('button',name='Discard layout edits',exact=True).click()
        expect(self.page.get_by_label('Tiles across',exact=True)).to_have_value('1')
        self.page.get_by_label('Active user profile',exact=True).select_option('admin')
        expect(self.page.get_by_label('Tiles across',exact=True)).to_have_value('4')
        expect(self.page.get_by_label('Minimum tile width (pixels)',exact=True)).to_have_value('360')
        self.page.get_by_role('tab',name='All',exact=True).click();self.page.evaluate("document.documentElement.style.fontSize='200%'")
        expect(self.page.locator('#all-grid')).to_have_attribute('data-columns','1')
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'));self.assertEqual(self.errors,[])

    def test_conflicting_session_and_profile_switch_discards_draft(self):
        other=self.store.save_profile({'name':'Guest'})['id'];self.open_all();self.setup_layout()
        self.page.get_by_label('Tiles across',exact=True).select_option('2')
        # Another context updates the selected profile while this form has an edit.
        c=self.store.configuration_document();body={k:copy.deepcopy(c[k]) for k in ('locations','devices','dashboard')}
        body['dashboard']['title']='Changed elsewhere';self.store.replace_configuration(body,self.store.configuration_etag())
        self.page.get_by_role('button',name='Save All layout',exact=True).click();expect(self.page.locator('#conflict')).to_be_visible()
        self.page.get_by_role('button',name='Reload & reapply edit',exact=True).click();expect(self.page.locator('#conflict')).to_be_hidden()
        expect(self.page.get_by_label('Tiles across',exact=True)).to_have_value('2')
        self.assertEqual(self.store.configuration_document()['dashboard']['title'],'Changed elsewhere')
        self.page.get_by_label('Tiles across',exact=True).select_option('6')
        self.page.get_by_label('Active user profile',exact=True).select_option(other)
        expect(self.page.get_by_label('Tiles across',exact=True)).to_have_value('0')
        self.page.get_by_label('Active user profile',exact=True).select_option('admin')
        expect(self.page.get_by_label('Tiles across',exact=True)).to_have_value('2');self.assertEqual(self.errors,[])

    def test_auto_and_all_explicit_counts(self):
        self.page.set_viewport_size(dict(width=1800,height=1000));self.open_all()
        for columns in range(7):
            self.save_layout(columns,240);self.page.get_by_role('tab',name='All',exact=True).click()
            expect(self.page.locator('#all-grid')).to_have_attribute('data-columns',str(columns or 2))
            self.assertEqual(self.page.locator('.sensor-tile').count(),2)
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.save_layout(0,640);self.page.get_by_role('tab',name='All',exact=True).click()
        self.page.set_viewport_size(dict(width=768,height=1024))
        expect(self.page.locator('#all-grid')).to_have_attribute('data-columns','1')
        self.assertEqual(self.errors,[])
