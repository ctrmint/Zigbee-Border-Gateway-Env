"""Opt-in React/Mantine/GridStack prototype browser acceptance, synthetic devices only."""
import copy
import time
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
        self.assertEqual(self.page.locator('.reading-card button,.reading-card a,.reading-card input').count(),0)
        for width,height in ((1440,1000),(1024,768),(768,1024),(390,844)):
            self.page.set_viewport_size(dict(width=width,height=height))
            expect(self.page.locator('.reading-card')).to_have_count(3)
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.page.screenshot(path='/tmp/issue34-mobile.png',full_page=True)
        self.page.set_viewport_size(dict(width=1440,height=1000))
        self.page.screenshot(path='/tmp/issue34-desktop.png',full_page=True)
        self.assertTrue(all(m=='GET' for m,u in self.sent))
        self.assertFalse(any('/commands' in u for _,u in self.sent))
        self.assertEqual(self.errors,[])

    def test_radio_dashboard_is_readonly_and_responsive(self):
        device=self.sim.devices[1]
        self.poller.radio={"status":"available","source":"simulated_coordinator_local_tables",
            "observed_at":time.time(),"mode":"simulator","ready":True,
            "uptime_ms":60000,"channel":20,"pan_id":0x1a62,"dropped_events":0,"latest_seq":self.sim.seq,
            "scope":"simulated_coordinator_local_tables",
            "neighbor_source":"synthetic_fixture_not_radio_observation",
            "route_source":"synthetic_fixture_not_radio_observation",
            "neighbors":[{"ieee":device['ieee'],"nwk":device['nwk'],"device_type":2,"depth":1,
                "rx_on_when_idle":False,"relationship":1,"lqi":180,"rssi_dbm":-48,
                "outgoing_cost":2,"age_periods":0,"device_timeout_seconds":0,"timeout_ms":0}],
            "routes":[{"destination_nwk":device['nwk'],"next_hop_nwk":device['nwk'],"state":0,
                "no_route_cache":False,"many_to_one":False,"route_record_required":False}],
            "route_records":[{"destination_nwk":device['nwk'],"relay_count":1,"path":[device['nwk']]}]}
        self.connect()
        self.page.get_by_role('button',name='Radio',exact=True).click()
        expect(self.page.get_by_role('heading',name='Radio',exact=True)).to_be_visible()
        expect(self.page.get_by_role('heading',name='Coordinator links',exact=True)).to_be_visible()
        expect(self.page.get_by_text('180',exact=True)).to_be_visible()
        expect(self.page.get_by_text('Retries / delivery failures',exact=True)).to_be_visible()
        for width,height in ((1024,768),(768,1024),(390,844)):
            self.page.set_viewport_size(dict(width=width,height=height))
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.assertTrue(all(method=='GET' for method,_ in self.sent))
        self.assertFalse(any('/api/v1/commands' in url for _,url in self.sent))
        self.assertEqual(self.errors,[])

    def test_starlink_dashboard_and_setup_are_readonly_and_responsive(self):
        current = self.store.starlink_configuration()
        settings = {key: current[key] for key in ("enabled", "host", "port", "dish_enabled", "dish_host", "dish_port")}
        settings.update(enabled=True, dish_enabled=True)
        self.store.replace_starlink_configuration(settings, self.store.starlink_etag())
        self.store.starlink_record("available", time.time(),
            router={"hardware_version": "v2", "software_version": "2026.20.0"},
            networks=[{"domain": "lan", "ipv4": "192.168.1.0/24", "ipv6": [],
                "clients_ethernet": 1, "clients_2ghz": 2, "clients_5ghz": 3}])
        self.store.starlink_dish_record("available", time.time(), metrics={
            "state":"CONNECTED", "pop_ping_latency_ms":28.5, "pop_ping_drop_rate":0.01,
            "downlink_throughput_bps":9_000_000, "uplink_throughput_bps":800_000,
            "snr":None, "fraction_obstructed":0.02, "currently_obstructed":False})
        self.connect()
        tabs = self.page.get_by_role('button', name='System', exact=True)
        self.assertTrue(tabs.is_visible())
        self.page.get_by_role('button', name='Starlink', exact=True).click()
        expect(self.page.get_by_role('heading', name='Starlink', exact=True)).to_be_visible()
        expect(self.page.get_by_text('2026.20.0', exact=True)).to_be_visible()
        expect(self.page.get_by_text('192.168.1.0/24', exact=True)).to_be_visible()
        expect(self.page.get_by_role('heading', name='Satellite link performance', exact=True)).to_be_visible()
        expect(self.page.get_by_text('28.5 ms', exact=True)).to_be_visible()
        for width,height in ((1024,768),(768,1024),(390,844)):
            self.page.set_viewport_size(dict(width=width,height=height))
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.page.get_by_role('button', name='Configuration & Setup', exact=True).click()
        self.page.get_by_role('tab', name='Starlink', exact=True).click()
        expect(self.page.get_by_label('Router private IPv4 address')).to_have_value('192.168.1.1')
        self.page.get_by_label('Router private IPv4 address').fill('192.168.1.2')
        self.page.get_by_label('Dish private IPv4 address').fill('192.168.100.2')
        self.page.get_by_role('button', name='Save Starlink settings', exact=True).click()
        expect(self.page.get_by_role('status')).to_contain_text('Saved')
        self.assertEqual(self.store.starlink_configuration()['host'], '192.168.1.2')
        self.assertEqual(self.store.starlink_configuration()['dish_host'], '192.168.100.2')
        self.assertTrue(all(method == 'GET' or (method == 'PUT' and '/api/v2/starlink/config' in url)
            for method,url in self.sent))
        self.assertFalse(any('/api/v1/commands' in url for _,url in self.sent))
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
        queries=[u for m,u in self.sent if '/api/v2/history?' in u and 'limit=500' in u]
        self.assertEqual(len(queries),1)
        self.page.get_by_role('button',name='South',exact=True).click()
        expect(self.page.locator('#location-overview')).to_contain_text('SNZB-02UL')
        expect(self.page.locator('#location-overview .reading-card')).to_have_count(1)
        self.page.set_viewport_size(dict(width=390,height=844))
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.page.get_by_role('button',name='All',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        self.page.wait_for_timeout(500);count=len([u for m,u in self.sent if '/api/v2/history?' in u]);self.page.wait_for_timeout(4500)
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
        self.page.get_by_role('button',name='Edit layout',exact=True).click()
        desktop=self.page.get_by_role('radio',name='Desktop',exact=True).get_attribute('id')
        self.page.locator('label[for="'+desktop+'"]').click()
        self.page.get_by_label('Width',exact=True).fill('3')
        self.page.get_by_role('button',name='Save location layout',exact=True).click()
        expect(self.page.get_by_role('button',name='Edit layout',exact=True)).to_be_enabled()
        geometry=self.store.configuration_document()['dashboard']['grid_layout']['locations'][self.north]['desktop']
        self.assertTrue(geometry)
        self.assertTrue(all(set(item)=={'id','x','y','w','h'} for item in geometry))
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

    def test_plug_rocker_debounces_and_compacts_controls(self):
        self.poller.status.update(plug_extensions=True)
        self.connect();self.setup_tab('Devices');self.page.get_by_role('button',name='S60ZBTPG',exact=True).click()
        self.assertFalse(any(m=='POST' for m,u in self.sent))
        rocker=self.page.get_by_role('switch',name='Relay for S60ZBTPG',exact=True)
        expect(rocker).to_be_checked()
        self.assertEqual(self.page.get_by_role('button',name='Request On',exact=True).count(),0)
        self.assertEqual(self.page.get_by_role('button',name='Request Off',exact=True).count(),0)
        self.page.evaluate("""() => {
          const rocker = document.querySelector('.relay-rocker');
          for (let i = 0; i < 3; i++)
            rocker.dispatchEvent(new MouseEvent('click', {bubbles: true}));
        }""")
        expect(self.page.get_by_role('button',name='Cancel plug operation',exact=True)).to_be_visible(timeout=10000)
        expect(rocker).to_be_disabled()
        jobs=self.store.plug_document()['jobs']
        relays=[j for j in jobs if j['action']=='relay']
        self.assertEqual(len(relays),1)
        self.assertEqual(relays[0]['settings'],{'state':False})
        self.assertEqual(self.page.locator('.plug-toggle-board .plug-toggle-cell').count(),1)
        self.assertEqual(self.page.locator('.plug-operations-grid').evaluate('(e) => getComputedStyle(e).display'),'grid')
        self.page.set_viewport_size({'width':1440,'height':1000})
        columns=self.page.locator('.plug-operations-grid').evaluate('(e) => getComputedStyle(e).gridTemplateColumns.split(" ").length')
        self.assertEqual(columns,4)
        self.page.set_viewport_size({'width':390,'height':844})
        expect(self.page.locator('.plug-operations-grid')).to_be_visible()
        tracks=self.page.locator('.plug-operations-grid').evaluate('(e) => getComputedStyle(e).gridTemplateColumns.split(" ").length')
        self.assertEqual(tracks,1)
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.page.set_viewport_size({'width':1440,'height':1000})
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

    def test_unknown_or_stale_relay_state_requires_refresh_before_toggle(self):
        self.poller.status.update(plug_extensions=True)
        def stale_relay(route):
            response=route.fetch();data=response.json()
            for device in data['devices']:
                if device['profile']=='SONOFF S60ZBTPG':
                    for measurement in device['measurements']:
                        if measurement['cluster']==6 and measurement['attribute']==0:
                            measurement['quality']='stale'
            route.fulfill(response=response,json=data)
        self.page.route('**/api/v2/devices',stale_relay)
        self.connect();self.setup_tab('Devices');self.page.get_by_role('button',name='S60ZBTPG',exact=True).click()
        rocker=self.page.locator('.relay-rocker')
        expect(rocker).to_be_disabled()
        self.assertIsNone(rocker.get_attribute('role'))
        expect(self.page.get_by_text('Relay state is stale. Read plug values before switching.',exact=True)).to_be_visible()
        self.page.get_by_role('button',name='Read plug values for S60ZBTPG',exact=True).click()
        expect(self.page.get_by_role('button',name='Cancel plug operation',exact=True)).to_be_visible(timeout=10000)
        self.assertTrue(any(j['action']=='read' for j in self.store.plug_document()['jobs']))
        self.assertEqual(self.errors,[])

    def test_location_plug_uses_the_same_confirmed_state_rocker(self):
        self.poller.status.update(plug_extensions=True)
        location=self.store.save_location('Utility room')['id']
        self.store.assign_location(self.sim.devices[-1]['ieee'],location)
        self.page.set_viewport_size({'width':1024,'height':768})
        self.connect()
        self.page.get_by_role('button',name='Utility room',exact=True).click()
        rocker=self.page.get_by_role('switch',name='Relay for S60ZBTPG',exact=True)
        expect(rocker).to_be_checked()
        self.assertEqual(self.page.locator('.plug-controls-section .plug-toggle-board .plug-toggle-cell').count(),1)
        self.assertEqual(self.page.locator('.plug-operation-section .plug-operations-grid .plug-operation-panel').count(),1)
        self.assertFalse(any(m=='POST' for m,u in self.sent))
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        self.assertEqual(self.errors,[])

    def test_opening_device_panels_never_writes_and_offline_disables_actions(self):
        self.poller.status.update(plug_extensions=True,reporting_commissioning=True,sensor_extensions=True)
        before=self.store.configuration_document();self.connect();self.setup_tab('Devices')
        for name in ('SNZB-02UL','S60ZBTPG'):
            self.page.get_by_role('button',name=name,exact=True).click()
        self.assertTrue(all(m=='GET' for m,u in self.sent))
        self.assertEqual(self.store.configuration_document(),before)
        self.poller.status['connected']=False
        expect(self.page.get_by_role('switch',name='Relay for S60ZBTPG',exact=True)).to_be_disabled(timeout=10000)
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


    def test_metric_typography_scale_preview_save_and_reset(self):
        self.page.set_viewport_size(dict(width=1440,height=1000));self.connect()
        self.page.get_by_role('button',name='Edit layout',exact=True).click()
        self.page.get_by_label('Content scale (%)',exact=True).fill('125')
        self.page.get_by_label('Metric font size (px)',exact=True).fill('60')
        self.page.get_by_role('combobox',name='Metric typeface',exact=True).click()
        self.page.get_by_role('option',name='Monospace',exact=True).click()
        self.page.get_by_label('Metric colour (hex)',exact=True).fill('#38cdec')
        expect(self.page.locator('.typography-preview .metric-reading')).to_have_css('font-size','75px')
        self.page.get_by_role('button',name='Save layout',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        p=self.store.configuration_document()['dashboard']['grid_layout']['presentation']
        identity=next(iter(p['all']));self.assertEqual(p['all'][identity],dict(scale=125,size=60,font='mono',color='#38cdec'))
        value=self.page.locator('[data-sensor-id="'+identity+'"] .measurement-value').first
        expect(value).to_have_css('font-size','75px');expect(value).to_have_css('color','rgb(56, 205, 236)')
        self.page.reload();self.connect();expect(self.page.locator('[data-sensor-id="'+identity+'"] .measurement-value').first).to_have_css('font-size','75px')
        self.page.get_by_role('button',name='Edit layout',exact=True).click()
        self.page.get_by_role('button',name='Use profile defaults',exact=True).click()
        self.page.get_by_role('button',name='Save layout',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout']['presentation']['all'],{})
        self.assertTrue(all(m=='GET' or (m=='PUT' and '/api/v2/configuration' in u) for m,u in self.sent));self.assertEqual(self.errors,[])

    def test_location_edit_navigation_guard_and_style_persistence(self):
        self.prepare_locations();self.connect()
        self.page.get_by_role('button',name='North',exact=True).click()
        self.page.get_by_role('button',name='Edit layout',exact=True).click()
        self.page.get_by_label('Metric font size (px)',exact=True).fill('64')
        self.page.get_by_label('Content scale (%)',exact=True).fill('125')
        self.page.get_by_role('button',name='All',exact=True).click()
        expect(self.page.get_by_role('dialog')).to_be_visible()
        self.page.get_by_role('button',name='Stay here',exact=True).click()
        expect(self.page.get_by_label('Metric font size (px)',exact=True)).to_have_value('64')
        self.page.get_by_role('button',name='Save location layout',exact=True).click()
        expect(self.page.get_by_role('button',name='Edit layout',exact=True)).to_be_enabled()
        style=self.store.configuration_document()['dashboard']['grid_layout']['presentation']
        self.assertEqual(style['widgets']['room-now']['size'],64)
        expect(self.page.locator('.location-numeric .metric-reading').first).to_have_css('font-size','80px')
        expect(self.page.locator('.location-widget .measurement-age').first).to_have_css('font-size','13.75px')
        self.page.get_by_role('button',name='Edit layout',exact=True).click()
        self.page.get_by_label('Metric font size (px)',exact=True).fill('90')
        self.page.get_by_role('button',name='Configuration & Setup',exact=True).click()
        self.page.get_by_role('button',name='Continue',exact=True).click()
        expect(self.page.get_by_role('tab',name='Gateway',exact=True)).to_be_visible()
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout']['presentation'],style)
        self.assertEqual(self.errors,[])

    def test_profile_default_typography_contrast_guidance_and_override(self):
        self.connect();self.page.get_by_role('button',name='Edit layout',exact=True).click()
        self.page.get_by_role('combobox',name='Appearance scope',exact=True).click()
        self.page.get_by_role('option',name='Profile defaults',exact=True).click()
        self.page.get_by_label('Metric font size (px)',exact=True).fill('54')
        self.page.get_by_label('Metric colour (hex)',exact=True).fill('#152538')
        expect(self.page.get_by_text('Low contrast against the panel background.',exact=False)).to_be_visible()
        self.page.get_by_role('button',name='Automatic colour',exact=True).click()
        self.page.get_by_role('button',name='Save layout',exact=True).click()
        expect(self.page.locator('#all-overview')).to_be_visible()
        self.assertEqual(self.store.configuration_document()['dashboard']['grid_layout']['presentation']['defaults']['size'],54)
        self.assertNotIn('presentation',self.store.configuration_document(self.other)['dashboard']['grid_layout'])
        self.assertEqual(self.errors,[])


    def test_all_history_is_bounded_cached_and_hidden_work_is_cancelled(self):
        self.connect();expect(self.page.locator('.mini-trend')).to_have_count(3)
        initial=[u for m,u in self.sent if '/api/v2/history?' in u]
        self.assertTrue(initial);self.assertTrue(all('limit=120' in u for u in initial))
        self.page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:true}); document.dispatchEvent(new Event('visibilitychange'))")
        count=len(initial);self.page.wait_for_timeout(4500)
        self.assertEqual(len([u for m,u in self.sent if '/api/v2/history?' in u]),count)
        self.page.evaluate("Object.defineProperty(document,'hidden',{configurable:true,value:false}); document.dispatchEvent(new Event('visibilitychange'))")
        self.page.wait_for_timeout(500)
        self.assertEqual(len([u for m,u in self.sent if '/api/v2/history?' in u]),count)
        self.assertTrue(all(m=='GET' for m,u in self.sent));self.assertEqual(self.errors,[])
