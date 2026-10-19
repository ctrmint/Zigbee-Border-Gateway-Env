"""Opt-in React/Mantine/GridStack prototype browser acceptance, synthetic devices only."""
import copy
from playwright.sync_api import expect
import browser_support as base


class DashboardTests(base.BrowserFixture):
    test_location_workflow_and_mobile_layout=None
    test_logout_during_pending_refresh=None

    def setUp(self):
        super().setUp();self.sim.add_snzb02ul();self.sim.add_s60zbtpg()
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.other=self.store.save_profile({'name':'Tablet'})['id']
        self.sent=[];self.page.on('request',lambda r:self.sent.append((r.method,r.url)))
        self.page.goto(f'http://127.0.0.1:{self.server.server_port}/')

    def connect(self):
        self.page.get_by_label('Dashboard access token',exact=True).fill(base.TOKEN)
        self.page.get_by_role('button',name='Connect to your home',exact=True).click()
        expect(self.page.locator('.reading-card')).to_have_count(3)

    def edit(self):
        self.page.get_by_role('button',name='Configuration & Setup',exact=True).click()
        self.page.get_by_role('tab',name='Preferences',exact=True).click()
        self.page.get_by_role('button',name='Edit All dashboard layout',exact=True).click()
        expect(self.page.get_by_role('button',name='Save layout',exact=True)).to_be_visible()

    def test_render_responsive_readonly_no_commands(self):
        self.connect()
        self.assertEqual(self.page.locator('#all-overview button,#all-overview a,#all-overview input').count(),0)
        for width,height in ((1440,1000),(1024,768),(768,1024),(390,844)):
            self.page.set_viewport_size(dict(width=width,height=height))
            expect(self.page.locator('.reading-card')).to_have_count(3)
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.page.screenshot(path='/tmp/issue34-mobile.png',full_page=True)
        self.page.set_viewport_size(dict(width=1440,height=1000))
        self.page.screenshot(path='/tmp/issue34-desktop.png',full_page=True)
        self.assertTrue(all(m=='GET' for m,u in self.sent))
        self.assertFalse(any('/history' in u or '/commands' in u for _,u in self.sent))
        self.assertEqual(self.errors,[])

    def test_save_keyboard_resize_theme_discard_and_reload(self):
        self.page.set_viewport_size(dict(width=1440,height=1000));self.connect();self.edit()
        self.page.get_by_label('Width',exact=True).fill('6')
        self.page.get_by_label('Height',exact=True).fill('6')
        theme_id=self.page.get_by_role('radio',name='Dark',exact=True).get_attribute('id')
        self.page.locator('label[for="'+theme_id+'"]').click()
        self.page.get_by_role('button',name='Save layout',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        layout=self.store.configuration_document()['dashboard']['grid_layout']
        self.assertEqual(layout['theme'],'dark');self.assertEqual(layout['all']['desktop'][0]['w'],6)
        self.page.reload();self.connect()
        expect(self.page.locator('html')).to_have_attribute('data-mantine-color-scheme','dark')
        self.edit();self.page.get_by_label('Width',exact=True).fill('3')
        self.page.get_by_role('button',name='Discard changes',exact=True).click()
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout'],layout)
        self.assertEqual(self.errors,[])

    def test_conflict_explicit_reapply_and_profile_isolation(self):
        self.page.set_viewport_size(dict(width=1440,height=1000));self.connect();self.edit()
        self.page.get_by_label('Width',exact=True).fill('6')
        c=self.store.configuration_document();body={k:copy.deepcopy(c[k]) for k in ('locations','devices','dashboard')};body['dashboard']['title']='Changed elsewhere';body['dashboard']['grid_layout']['locations']={'room':{'desktop':[dict(id='other-widget',x=0,y=0,w=4,h=4)],'tablet':[],'mobile':[]}}
        self.store.replace_configuration(body,self.store.configuration_etag())
        self.page.get_by_role('button',name='Save layout',exact=True).click()
        expect(self.page.get_by_text('Layout not saved',exact=True)).to_be_visible()
        self.page.get_by_role('button',name='Reapply layout to latest configuration',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        self.assertEqual(self.store.configuration_document()['dashboard']['title'],'Changed elsewhere')
        self.assertIn('room',self.store.configuration_document()['dashboard']['grid_layout']['locations'])
        self.assertEqual(self.store.configuration_document(self.other)['dashboard']['grid_layout']['all']['desktop'],[])
        self.assertTrue(all(m=='GET' or (m=='PUT' and '/api/v2/configuration' in u) for m,u in self.sent))
        self.assertEqual(self.errors,[])

    def test_profile_switch_discards_draft_and_disconnect_clears_data(self):
        self.page.set_viewport_size(dict(width=1440,height=1000));self.connect();self.edit()
        self.page.get_by_label('Width',exact=True).fill('6')
        self.page.get_by_role('combobox',name='Active user profile',exact=True).click()
        self.page.get_by_role('option',name='Tablet',exact=True).click()
        self.page.get_by_role('button',name='Continue',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout']['all']['desktop'],[])
        self.page.get_by_role('button',name='Disconnect',exact=True).click()
        expect(self.page.locator('.reading-card')).to_have_count(0)
        expect(self.page.get_by_label('Dashboard access token',exact=True)).to_be_visible()
        count=len(self.sent);self.page.wait_for_timeout(4500);self.assertEqual(len(self.sent),count)
        self.assertEqual(self.errors,[])

    def test_drag_geometry_saved_only_after_explicit_save(self):
        self.page.set_viewport_size(dict(width=1440,height=1000));self.connect();self.edit()
        grip=self.page.locator('.tile-handle').first
        grip.scroll_into_view_if_needed();box=grip.bounding_box()
        before=self.store.configuration_document()['dashboard']['grid_layout']
        self.page.mouse.move(box['x']+box['width']/2,box['y']+box['height']/2)
        self.page.mouse.down();self.page.mouse.move(box['x']+box['width']/2+120,box['y']+box['height']/2+80,steps=15);self.page.mouse.up()
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout'],before)
        self.page.get_by_role('button',name='Save layout',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        geometry=self.store.configuration_document()['dashboard']['grid_layout']['all']['desktop']
        self.assertTrue(any(n['x'] or n['y'] for n in geometry))
        self.assertEqual(self.errors,[])

    def test_departed_returning_devices_and_stable_polling(self):
        self.connect();self.page.evaluate("window.firstCard=document.querySelector('.reading-card')")
        departing=self.sim.devices[2];departing['active']=False
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        expect(self.page.locator('.reading-card')).to_have_count(2,timeout=10000)
        departing['active']=True
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        expect(self.page.locator('.reading-card')).to_have_count(3,timeout=10000)
        self.assertTrue(self.page.evaluate("window.firstCard===document.querySelector('.reading-card')"))
        self.assertTrue(all(m=='GET' for m,u in self.sent))
        self.assertEqual(self.errors,[])

    def test_deleted_active_profile_clears_draft_and_resolves_admin(self):
        self.connect()
        self.page.get_by_role('combobox',name='Active user profile',exact=True).click()
        self.page.get_by_role('option',name='Tablet',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        self.edit();self.page.get_by_label('Width',exact=True).fill('1')
        self.store.delete_profile(self.other)
        expect(self.page.locator('#all-overview')).to_be_visible(timeout=15000)
        expect(self.page.get_by_role('combobox',name='Active user profile',exact=True)).to_have_value('Admin')
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout']['all']['desktop'],[])
        self.assertEqual(self.errors,[])

    def prepare_locations(self):
        self.north=self.store.save_location('North')['id'];self.south=self.store.save_location('South')['id']
        self.store.assign_location(self.sim.devices[1]['ieee'],self.north)
        self.store.assign_location(self.sim.devices[2]['ieee'],self.south)
        c=self.store.configuration_document();body={k:copy.deepcopy(c[k]) for k in ('locations','devices','dashboard')}
        source=dict(ieee=self.sim.devices[1]['ieee'],endpoint=1,cluster=1026,attribute=0)
        body['dashboard']['widgets']=[dict(id='room-now',type='numeric',title='Temperature now',source=source,position=0,time_range=3600),dict(id='room-history',type='chart',title='Temperature history',source=source,position=1,time_range=3600),dict(id='same-history',type='chart',title='Another view of temperature',source=source,position=2,time_range=3600)]
        self.store.replace_configuration(body,self.store.configuration_etag())

    def test_locations_stay_in_preview_with_widgets_and_shared_history(self):
        self.prepare_locations();self.connect();url=self.page.url
        self.page.get_by_role('button',name='North',exact=True).click()
        expect(self.page.locator('#location-overview')).to_be_visible()
        expect(self.page.locator('#location-overview')).to_contain_text('Temperature now')
        expect(self.page.locator('#location-overview')).to_contain_text('20.5')
        expect(self.page.locator('#location-overview svg[role=img]')).to_have_count(2)
        self.assertEqual(self.page.url,url)
        queries=[u for m,u in self.sent if '/api/v2/history?' in u]
        self.assertEqual(len(queries),1)
        self.page.get_by_role('button',name='South',exact=True).click()
        expect(self.page.locator('#location-overview')).to_contain_text('SNZB-02UL')
        expect(self.page.locator('#location-overview .reading-card')).to_have_count(1)
        self.page.set_viewport_size(dict(width=390,height=844))
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.page.get_by_role('button',name='All',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        count=len([u for m,u in self.sent if '/api/v2/history?' in u]);self.page.wait_for_timeout(4500)
        self.assertEqual(len([u for m,u in self.sent if '/api/v2/history?' in u]),count)
        self.assertEqual(self.page.url,url)
        self.assertTrue(all(m=='GET' for m,u in self.sent));self.assertEqual(self.errors,[])

    def test_navigating_away_cancels_pending_location_history(self):
        import threading
        self.prepare_locations();self.history_delay=threading.Event();self.history_delay.set();self.connect()
        self.page.get_by_role('button',name='North',exact=True).click()
        self.assertTrue(self.waiting.wait(10))
        self.page.get_by_role('button',name='All',exact=True).click();self.release.set()
        expect(self.page.locator('#all-overview')).to_be_visible()
        expect(self.page.locator('#location-overview')).to_have_count(0)
        self.assertEqual(self.errors,[])

    def setup_tab(self,name):
        self.page.get_by_role('button',name='Configuration & Setup',exact=True).click()
        self.page.get_by_role('tab',name=name,exact=True).click()

    def test_setup_metadata_profiles_locations_preferences_and_no_radio_actions(self):
        self.connect();self.setup_tab('Locations')
        self.page.get_by_label('New location',exact=True).fill('Kitchen')
        self.page.get_by_role('button',name='Add location',exact=True).click()
        expect(self.page.get_by_label('Rename Kitchen',exact=True)).to_be_visible()
        location=self.store.locations()[0]['id']
        self.page.get_by_role('tab',name='Preferences',exact=True).click()
        self.page.get_by_label('Dashboard title',exact=True).fill('Test home')
        self.page.get_by_role('button',name='Save preferences',exact=True).click()
        expect(self.page.locator('.page-heading h1')).to_contain_text('Test home')
        self.page.get_by_role('tab',name='Profiles',exact=True).click()
        self.page.get_by_label('New profile name',exact=True).fill('Guest')
        self.page.get_by_role('button',name='Add profile',exact=True).click()
        expect(self.page.get_by_label('Rename profile Guest',exact=True)).to_be_visible(timeout=10000)
        self.page.get_by_role('tab',name='Devices',exact=True).click()
        self.page.get_by_role('button',name='SNZB-02UL',exact=True).click()
        identity=self.sim.devices[2]['ieee']
        self.page.get_by_label('Name for '+identity,exact=True).fill('Room sensor')
        self.page.get_by_role('combobox',name='Location for '+identity,exact=True).click()
        self.page.get_by_role('option',name='Kitchen',exact=True).click()
        self.page.get_by_role('button',name='Save device settings',exact=True).click()
        expect(self.page.get_by_role('button',name='Room sensor',exact=True)).to_be_visible(timeout=10000)
        self.assertEqual(self.store.configuration_document()['devices'][identity]['location_id'],location)
        self.assertFalse(any('/api/v1/commands' in u or '/api/v2/plugs' in u or '/api/v2/commissioning' in u and m=='POST' for m,u in self.sent))
        self.assertEqual(self.errors,[])

    def test_widget_editor_range_order_and_location_geometry(self):
        self.prepare_locations();self.connect();self.page.get_by_role('button',name='North',exact=True).click()
        self.page.get_by_role('button',name='Add widget',exact=True).click()
        self.page.get_by_label('Widget title',exact=True).fill('New reading')
        self.page.get_by_role('button',name='Save widget',exact=True).click()
        expect(self.page.get_by_role('heading',name='New reading',exact=True)).to_be_visible()
        self.page.get_by_role('button',name='Arrange widgets',exact=True).click()
        desktop=self.page.get_by_role('radio',name='Desktop',exact=True).get_attribute('id')
        self.page.locator('label[for="'+desktop+'"]').click()
        self.page.get_by_label('Width',exact=True).fill('3')
        self.page.get_by_role('button',name='Save location layout',exact=True).click()
        expect(self.page.get_by_role('button',name='Arrange widgets',exact=True)).to_be_enabled()
        self.assertTrue(self.store.configuration_document()['dashboard']['grid_layout']['locations'][self.north]['desktop'])
        widget=self.page.locator('.location-widget').filter(has=self.page.get_by_role('heading',name='New reading',exact=True))
        widget.get_by_role('button',name='Edit',exact=True).click()
        self.page.get_by_label('Widget title',exact=True).fill('Renamed reading')
        self.page.get_by_role('button',name='Save widget',exact=True).click()
        expect(self.page.get_by_role('heading',name='Renamed reading',exact=True)).to_be_visible()
        self.assertEqual(self.errors,[])

    def test_sensor_reporting_and_display_requests_are_explicit(self):
        self.poller.status.update(reporting_commissioning=True,sensor_extensions=True,plug_extensions=True)
        self.connect();self.setup_tab('Devices');self.page.get_by_role('button',name='SNZB-02UL',exact=True).click()
        self.page.get_by_role('button',name='Reporting configuration',exact=True).click()
        self.assertFalse(any(m=='POST' for m,u in self.sent))
        self.page.get_by_role('button',name='Configure reporting',exact=True).click()
        expect(self.page.get_by_role('button',name='Cancel reporting setup',exact=True)).to_be_visible(timeout=10000)
        job=self.store.commissioning_document()['jobs'][0]
        self.assertEqual(job['policy']['model_hint'],'SONOFF SNZB-02UL')
        self.page.get_by_role('button',name='Cancel reporting setup',exact=True).click()
        self.page.get_by_role('button',name='SNZB-02UL E-Ink settings',exact=True).click()
        self.page.get_by_role('button',name='Apply display setting',exact=True).click()
        expect(self.page.get_by_role('button',name='Cancel display setup',exact=True)).to_be_visible(timeout=10000)
        self.assertEqual(len([u for m,u in self.sent if m=='POST' and '/api/v2/display' in u]),1)
        self.assertEqual(self.errors,[])

    def test_plug_controls_queue_once_with_protection_limits_and_no_load_on_view(self):
        self.poller.status.update(plug_extensions=True)
        self.connect();self.setup_tab('Devices');self.page.get_by_role('button',name='S60ZBTPG',exact=True).click()
        self.assertFalse(any(m=='POST' for m,u in self.sent))
        self.page.get_by_role('button',name='Request On',exact=True).click()
        expect(self.page.get_by_role('button',name='Cancel plug operation',exact=True)).to_be_visible(timeout=10000)
        self.page.get_by_role('button',name='Cancel plug operation',exact=True).click()
        self.page.get_by_role('button',name='Protection thresholds · 13 A / 3250 W maximum',exact=True).click()
        self.page.get_by_label('Maximum current (A)',exact=True).fill('13')
        self.page.get_by_label('Maximum power (W)',exact=True).fill('3250')
        self.page.get_by_role('button',name='Apply protection thresholds',exact=True).click()
        expect(self.page.get_by_role('button',name='Cancel plug operation',exact=True)).to_be_visible(timeout=10000)
        jobs=self.store.plug_document()['jobs'];protection=next(j for j in jobs if j['action']=='protection')
        self.assertEqual(protection['settings']['max_current'],13)
        self.assertEqual(protection['settings']['max_power'],3250)
        self.assertEqual(len([j for j in jobs if j['action']=='relay']),1)
        self.assertEqual(self.errors,[])

    def test_opening_device_panels_never_writes_and_offline_disables_actions(self):
        self.poller.status.update(plug_extensions=True,reporting_commissioning=True,sensor_extensions=True)
        before=self.store.configuration_document();self.connect();self.setup_tab('Devices')
        for name in ('SNZB-02UL','S60ZBTPG'):
            self.page.get_by_role('button',name=name,exact=True).click()
        self.assertTrue(all(m=='GET' for m,u in self.sent))
        self.assertEqual(self.store.configuration_document(),before)
        self.poller.status['connected']=False
        expect(self.page.get_by_role('button',name='Request On',exact=True)).to_be_disabled(timeout=10000)
        self.assertEqual(self.errors,[])

    def test_all_keeps_invalid_stale_zero_and_low_battery_distinct(self):
        import time
        def values(route):
            response=route.fetch();data=response.json()
            for device in data['devices']:
                for m in device['measurements']:
                    if device['ieee']==self.sim.devices[1]['ieee'] and m['cluster']==1026:m.update(value=None,quality='invalid')
                    if device['ieee']==self.sim.devices[1]['ieee'] and m['cluster']==1029:m.update(value=0,quality='stale',received_at=time.time()-100000)
                    if device['ieee']==self.sim.devices[2]['ieee'] and m['cluster']==1 and m['attribute']==33:m.update(value=10,low_battery=True)
            route.fulfill(response=response,json=data)
        self.page.route('**/api/v2/devices',values);self.connect()
        expect(self.page.locator('#all-overview')).to_contain_text('Invalid reading')
        expect(self.page.locator('#all-overview')).to_contain_text('Stale')
        expect(self.page.locator('#all-overview')).to_contain_text('Low battery')
        expect(self.page.locator('[data-quality="stale"] .measurement-value').first).to_have_text('0')
        self.assertTrue(all(m=='GET' for m,u in self.sent));self.assertEqual(self.errors,[])

    def test_reporting_policy_loads_asynchronously_without_overwriting_edits(self):
        policy=dict(ieee=self.sim.devices[2]['ieee'],endpoint=1,min_interval=7,max_interval=2700,temperature_change=.3,humidity_change=2,model_hint='SONOFF SNZB-02UL')
        self.store.start_commissioning(policy);expose=[False]
        def delayed(route):
            if expose[0]:route.continue_()
            else:route.fulfill(status=200,json={'jobs':[]})
        self.page.route('**/api/v2/commissioning',delayed)
        self.connect();self.setup_tab('Devices');self.page.get_by_role('button',name='SNZB-02UL',exact=True).click()
        self.page.get_by_role('button',name='Reporting configuration',exact=True).click();expose[0]=True
        maximum=self.page.get_by_label('Maximum report interval (seconds)',exact=True)
        expect(maximum).to_have_value('2700',timeout=10000)
        maximum.fill('2800');self.page.wait_for_timeout(3500);expect(maximum).to_have_value('2800')
        self.assertTrue(all(m=='GET' for m,u in self.sent));self.assertEqual(self.errors,[])
