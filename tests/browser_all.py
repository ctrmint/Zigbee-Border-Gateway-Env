"""Read-only All overview: synthetic sensors, dense tablet layout and stable updates."""
import copy
import json
import time
from playwright.sync_api import expect
import browser_locations as base


class AllTests(base.BrowserLocationTests):
    test_location_workflow_and_mobile_layout = None
    test_logout_during_pending_refresh = None

    def setUp(self):
        super().setUp()
        self.sensor=self.sim.devices[1]['ieee']
        self.room=self.store.save_location('Garage')
        self.store.assign_location(self.sensor,self.room['id'])
        self.sent=[]
        self.page.on('request',lambda r:self.sent.append((r.method,r.url)))

    def open_all(self):
        self.connect()
        self.page.get_by_role('tab',name='All',exact=True).click()
        expect(self.page.locator('#all-panel')).to_be_visible()
        expect(self.page.locator('#location-panel')).to_be_hidden()
        expect(self.page.locator('#setup-panel')).to_be_hidden()

    def add_synthetic_sensor(self):
        # Descriptor and battery response are explicit test data, not #14 backend support.
        d={'ieee':'00124b0000000014','nwk':0x3414,'active':True}
        self.sim.devices.append(d);self.sim.emit(dict(d,type='announce'))
        self.sim.emit(dict(d,type='endpoint',endpoint=1,ok=True,profile_id=260,device_id=770,input_clusters=[1,6,1026,1029],output_clusters=[]))
        self.sim.attr(2,1026,0x29,2150);self.sim.attr(2,1029,0x21,4820)
        def battery_response(route):
            response=route.fetch();doc=response.json()
            for device in doc['devices']:
                if device['ieee']==d['ieee']:
                    device['measurements'].append({'endpoint':1,'cluster':1,'attribute':33,'label':'Battery','value':10,'unit':'%','received_at':time.time(),'quality':'valid','freshness_seconds':172800,'low_battery':True})
            route.fulfill(response=response,json=doc)
        self.page.route('**/api/v2/devices',battery_response)

    def update(self):
        self.store.ingest(self.sim.boot,self.sim.events,self.sim.seq,self.sim.devices)
        self.page.evaluate('refresh()')

    def test_read_only_capabilities_and_no_extra_requests(self):
        before=self.store.configuration_document()
        self.open_all()
        expect(self.page.locator('.sensor-tile')).to_have_count(1)  # Plug is not a sensor.
        expect(self.page.locator('.sensor-tile')).to_contain_text('Garage')
        expect(self.page.locator('.sensor-tile')).to_contain_text('20.5')
        expect(self.page.locator('.sensor-tile')).to_contain_text('48')
        self.assertEqual(self.page.locator('#all-panel button,#all-panel a,#all-panel input,#all-panel select,#all-panel [tabindex],#all-panel summary').count(),0)
        self.assertEqual(self.store.configuration_document(),before)
        self.assertFalse(any('/commands' in u or '/history' in u for _,u in self.sent))
        self.assertFalse(any(m!='GET' for m,_ in self.sent))
        self.page.get_by_role('tab',name='Configuration & Setup',exact=True).click()
        expect(self.page.locator('#setup-panel')).to_be_visible()
        self.page.get_by_role('tab',name='All',exact=True).click()
        self.page.get_by_role('button',name='Disconnect',exact=True).click()
        expect(self.page.locator('#all-panel')).to_be_hidden()
        expect(self.page.locator('#all-grid')).to_be_empty()
        self.assertFalse(self.page.evaluate("document.body.classList.contains('overview-mode')"))
        self.assertEqual(self.errors,[])

    def test_mixed_endpoints_unassigned_and_battery_states(self):
        self.add_synthetic_sensor()
        self.update()
        # A temperature-only probe with a second temperature endpoint; no humidity placeholder.
        probe={'ieee':'00124b0000000018','nwk':0x1818,'active':True};self.sim.devices.append(probe)
        self.sim.emit(dict(probe,type='announce'))
        for ep in (1,2):
            self.sim.emit(dict(probe,type='endpoint',endpoint=ep,ok=True,profile_id=260,device_id=770,input_clusters=[1026],output_clusters=[]))
        self.sim.emit(dict(probe,type='attribute',endpoint=1,cluster=1026,attribute=0,data_type=0x29,raw=1800,origin='report'))
        self.sim.emit(dict(probe,type='attribute',endpoint=2,cluster=1026,attribute=0,data_type=0x29,raw=-32768,origin='report'))
        self.update();self.open_all()
        expect(self.page.locator('.sensor-tile')).to_have_count(3)
        ul=self.page.locator('[data-sensor-id="00124b0000000014"]')
        expect(ul).to_contain_text('Unassigned');expect(ul).to_contain_text('Low battery')
        expect(ul.locator('.sensor-battery .sensor-value')).to_have_text('10')
        self.assertNotIn('voltage',ul.inner_text().lower())
        p=self.page.locator('[data-sensor-id="00124b0000000018"]')
        expect(p).to_contain_text('EP 1');expect(p).to_contain_text('EP 2');expect(p).to_contain_text('Invalid reading')
        self.assertNotIn('Humidity',p.inner_text())
        self.assertNotIn('On',ul.locator('dt').all_text_contents())
        self.assertEqual(self.errors,[])

    def test_updates_stale_offline_missing_and_stable_nodes(self):
        self.open_all();tile=self.page.locator('.sensor-tile')
        self.page.evaluate("window.originalTile=document.querySelector('.sensor-tile')")
        with self.store.lock,self.store.db:
            d=self.store._get(self.sensor)
            d['attributes']['1:1026:0']['received']=time.time()-7200
            del d['attributes']['1:1029:0']
            self.store._put(d)
        self.page.evaluate('refresh()')
        expect(tile).to_contain_text('Stale');expect(tile).to_contain_text('No reading')
        self.assertTrue(self.page.evaluate("originalTile===document.querySelector('.sensor-tile')"))
        config=self.store.configuration_document()
        config['devices'][self.sensor]['freshness_seconds']=10000
        self.store.replace_configuration({k:config[k] for k in ('locations','devices','dashboard')},f'"configuration-{config["revision"]}"')
        self.page.evaluate('refresh()')
        expect(tile.locator('[data-quality="valid"] .sensor-value')).to_have_text('20.5')
        self.poller.status['connected']=False;self.page.evaluate('refresh()')
        expect(self.page.locator('#all-connection')).to_contain_text('Gateway offline')
        # A dashboard API outage also marks cached readings offline rather than erasing them.
        self.page.route('**/api/v2/devices',lambda route:route.fulfill(status=503,content_type='application/json',body=json.dumps({'error':{'message':'Unavailable'}})))
        self.page.evaluate('refresh()');expect(tile).to_contain_text('20.5')
        expect(self.page.locator('#all-connection')).to_be_visible()
        self.page.unroute('**/api/v2/devices')
        self.poller.status['connected']=True
        self.sim.attr(1,1026,0x29,2300);self.update()
        expect(tile.locator('[data-quality="valid"] .sensor-value')).to_have_text('23')
        expect(self.page.locator('#all-connection')).to_be_hidden()
        self.assertEqual(self.errors,[])

    def test_dense_tablet_layout_long_names_zoom_and_scroll(self):
        # Clone a sensor fixture without ever inserting fake sensors into the live database.
        with self.store.lock,self.store.db:
            template=self.store._get(self.sensor)
            for i in range(30):
                d=copy.deepcopy(template);d['ieee']=f'{0x1800+i:016x}';self.store._put(d)
        config=self.store.configuration_document()
        for setting in config['devices'].values():setting['name']='Long sensor name '+('abcdefghijklmnopqrstuvwx'*2)
        self.store.replace_configuration({k:config[k] for k in ('locations','devices','dashboard')},f'"configuration-{config["revision"]}"')
        self.open_all()
        for width,height in ((1024,768),(768,1024),(1180,820),(507,820),(390,844)):
            self.page.set_viewport_size({'width':width,'height':height})
            self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
            rects=self.page.locator('.sensor-tile').evaluate_all('(nodes)=>nodes.map(n=>({x:n.getBoundingClientRect().x,y:n.getBoundingClientRect().y,width:n.getBoundingClientRect().width}))')
            if width>=768:self.assertGreaterEqual(sum(r['y']==rects[0]['y'] for r in rects),2)
            self.page.evaluate('window.scrollTo(0,800)')
            y=self.page.evaluate('scrollY');self.page.evaluate('refresh()')
            self.assertAlmostEqual(self.page.evaluate('scrollY'),y,delta=1)
        self.page.evaluate("document.documentElement.style.zoom='2'")
        self.page.set_viewport_size({'width':507,'height':820})
        self.assertTrue(self.page.evaluate('document.documentElement.scrollWidth<=innerWidth'))
        self.assertEqual(self.errors,[])

    def test_empty_and_preserve_default_navigation(self):
        with self.store.lock,self.store.db:
            d=self.store._get(self.sensor);d['active']=False;self.store._put(d)
        self.open_all();expect(self.page.locator('#all-empty')).to_be_visible()
        expect(self.page.locator('.sensor-tile')).to_have_count(0)
        self.page.get_by_role('button',name='Disconnect',exact=True).click();self.connect()
        expect(self.page.get_by_role('tab',name='Garage',exact=True)).to_have_attribute('aria-selected','true')
        self.assertEqual(self.errors,[])
