"""Cookie sessions, concurrent presentation state, late requests and tablet access."""
import json
from playwright.sync_api import expect
import browser_locations as base

class ProfileBrowserTests(base.BrowserLocationTests):
    test_location_workflow_and_mobile_layout=None
    test_logout_during_pending_refresh=None

    def setUp(self):
        super().setUp()
        self.room=self.store.save_location('Room')
        self.store.assign_location(self.sim.devices[1]['ieee'],self.room['id'])
        self.url=f'http://127.0.0.1:{self.server.server_port}'

    def add(self,name):return self.store.save_profile({'name':name})['id']
    def choose(self,profile,page=None):
        p=page or self.page;p.get_by_label('Active user profile').select_option(profile)
        p.wait_for_function('(id)=>activeProfile===id&&config!==null&&!refreshing',arg=profile)
    def setup_tab(self,page=None):
        (page or self.page).get_by_role('tab',name='Configuration & Setup',exact=True).click()
    def connect_page(self,p):
        p.goto(self.url);p.get_by_label('Dashboard access token').fill(base.TOKEN);p.get_by_role('button',name='Connect',exact=True).click()
        expect(p.get_by_label('Active user profile')).to_be_visible()
    def preferences(self,title,unit,page=None):
        p=page or self.page;self.setup_tab(p)
        p.get_by_label('Dashboard title',exact=True).fill(title);p.get_by_label('Temperature display').select_option(unit)
        p.get_by_role('button',name='Save preferences',exact=True).click();expect(p.locator('#home-title')).to_have_text(title)
        p.wait_for_function('()=>!saving&&!refreshing')

    def test_management_without_login_and_stable_ids(self):
        self.connect();self.setup_tab()
        expect(self.page.get_by_label('Active user profile')).to_have_value('admin')
        self.page.get_by_label('New profile name').fill('Alice')
        self.page.get_by_role('button',name='Add profile',exact=True).click()
        expect(self.page.get_by_label('Rename profile Alice')).to_be_visible()
        a=next(p['id'] for p in self.store.profiles_document()['profiles'] if p['name']=='Alice')
        self.choose(a);self.page.get_by_label('Rename profile Alice').fill('Alicia')
        self.page.get_by_role('button',name='Save profile name',exact=True).click()
        expect(self.page.get_by_label('Rename profile Alicia')).to_be_visible()
        self.assertEqual(self.page.get_by_label('Active user profile').input_value(),a)
        self.page.get_by_role('button',name='Delete profile',exact=True).click()
        expect(self.page.get_by_label('Active user profile')).to_have_value('admin')
        self.page.wait_for_function('()=>config!==null&&!refreshing')
        self.assertEqual(len(self.store.profiles_document()['profiles']),1)
        self.assertEqual(self.errors,[])

    def test_two_independent_sessions_preferences_and_widgets(self):
        a=self.add('Alice');b=self.add('Bob');admin=self.store.configuration_document()
        self.connect();self.choose(a);self.preferences('Alice dashboard','fahrenheit')
        self.page.get_by_role('tab',name='Room',exact=True).click()
        self.page.get_by_role('button',name='Add sensor widgets',exact=True).click()
        expect(self.page.locator('.widget')).to_have_count(4)
        context=self.browser.new_context();self.addCleanup(context.close);other=context.new_page()
        self.connect_page(other);self.choose(b,other);self.preferences('Bob dashboard','celsius',other)
        other.get_by_role('tab',name='All',exact=True).click()
        expect(other.locator('.sensor-reading').first).to_contain_text('°C')
        self.page.get_by_role('tab',name='All',exact=True).click()
        expect(self.page.locator('.sensor-reading').first).to_contain_text('°F')
        expect(self.page.locator('#home-title')).to_have_text('Alice dashboard')
        self.assertEqual(self.store.configuration_document(),admin)
        self.assertEqual(len(self.store.configuration_document(a)['dashboard']['widgets']),4)
        self.assertEqual(self.store.configuration_document(b)['dashboard']['widgets'],[])
        self.choose('admin');expect(self.page.locator('#home-title')).to_have_text(admin['dashboard']['title'])
        expect(other.locator('#home-title')).to_have_text('Bob dashboard')
        self.assertEqual(self.errors,[])

    def test_session_cookie_reload_and_new_session_default(self):
        a=self.add('Alice');self.connect();self.choose(a)
        cookie=next(c for c in self.page.context.cookies() if c['name']=='dashboard_profile')
        self.assertEqual(cookie['value'],a);self.assertEqual(cookie['expires'],-1);self.assertFalse(cookie['secure']);self.assertFalse(cookie['httpOnly']);self.assertEqual(cookie['path'],'/')
        self.page.reload();self.connect();expect(self.page.get_by_label('Active user profile')).to_have_value(a)
        context=self.browser.new_context();self.addCleanup(context.close);other=context.new_page();self.connect_page(other)
        expect(other.get_by_label('Active user profile')).to_have_value('admin')
        self.assertEqual(self.page.evaluate('localStorage.length+sessionStorage.length'),0)
        self.assertEqual(self.errors,[])

    def test_blocked_cookie_session_and_unknown_cookie_fallback(self):
        a=self.add('Alice')
        self.page.add_init_script("Object.defineProperty(Document.prototype,'cookie',{get(){return ''},set(v){},configurable:true})")
        self.page.reload();self.connect();self.choose(a);self.page.evaluate('refresh()')
        expect(self.page.get_by_label('Active user profile')).to_have_value(a)
        self.preferences('Ephemeral selection','fahrenheit')
        self.page.reload();self.connect();expect(self.page.get_by_label('Active user profile')).to_have_value('admin')
        context=self.browser.new_context();self.addCleanup(context.close)
        context.add_cookies([{'name':'dashboard_profile','value':'p-'+'f'*24,'url':self.url}]);p=context.new_page();self.connect_page(p)
        p.wait_for_function('()=>config!==null&&!refreshing');expect(p.get_by_label('Active user profile')).to_have_value('admin')
        self.assertEqual(self.errors,[])

    def test_shared_cookie_tab_changes_discard_editor_and_deleted_fallback(self):
        context=self.browser.new_context();self.addCleanup(context.close);self.page=context.new_page()
        a=self.add('Alice');b=self.add('Bob');self.connect_page(self.page);self.choose(a)
        self.page.get_by_role('tab',name='Room',exact=True).click()
        self.page.get_by_role('button',name='Add widget',exact=True).click();expect(self.page.locator('#widget-dialog')).to_be_visible()
        other=self.page.context.new_page();self.connect_page(other);self.choose(b,other)
        self.page.evaluate('refresh()')
        expect(self.page.get_by_label('Active user profile')).to_have_value(b);expect(self.page.locator('#widget-dialog')).to_be_hidden()
        self.page.wait_for_function('()=>config!==null&&!refreshing')
        self.store.delete_profile(b);self.page.evaluate('refresh()')
        expect(self.page.get_by_label('Active user profile')).to_have_value('admin')
        self.page.wait_for_function('()=>config!==null&&!refreshing');self.assertEqual(self.errors,[])

    def test_late_save_keeps_captured_profile_after_switch(self):
        a=self.add('Alice');b=self.add('Bob');self.connect();self.choose(a);self.setup_tab()
        held=[]
        def hold(route):
            if route.request.method=='PUT':held.append(route)
            else:route.continue_()
        self.page.route('**/api/v2/configuration',hold)
        self.page.get_by_label('Dashboard title',exact=True).fill('Late Alice save')
        self.page.get_by_role('button',name='Save preferences',exact=True).click()
        self.page.wait_for_function('()=>saving')
        self.assertEqual(len(held),1);request=held[0].request;headers=request.all_headers()
        self.assertEqual(headers['x-dashboard-profile'],a)
        self.choose(b);held[0].abort()
        # Model an already transmitted request reaching the server after selection changed.
        response=self.page.request.put(self.url+'/api/v2/configuration',data=request.post_data,headers={k:headers[k] for k in ['authorization','content-type','if-match','x-dashboard-profile']})
        self.assertEqual(response.status,200)
        expect(self.page.locator('#home-title')).to_have_text('Home')
        self.assertEqual(self.store.configuration_document(a)['dashboard']['title'],'Late Alice save')
        self.assertEqual(self.store.configuration_document(b)['dashboard']['title'],'Home')
        self.page.unroute('**/api/v2/configuration');self.assertEqual(self.errors,[])

    def test_profile_selector_tablet_layout_and_long_names(self):
        a=self.add('Long name '+('abcdefghijklmnopqrstuvwx'*2));self.connect();self.choose(a)
        for tab in ['All','Room','Configuration & Setup']:
            self.page.get_by_role('tab',name=tab,exact=True).click()
            for width,height in [(1024,768),(768,1024),(507,820),(390,844)]:
                self.page.set_viewport_size({'width':width,'height':height})
                expect(self.page.get_by_label('Active user profile')).to_be_visible()
                box=self.page.get_by_label('Active user profile').bounding_box()
                self.assertLessEqual(box['x']+box['width'],width)
                geometry=self.page.evaluate('({scroll:document.documentElement.scrollWidth,width:innerWidth})')
                self.assertLessEqual(geometry['scroll'],geometry['width'],(tab,width,geometry))
        self.assertEqual(self.errors,[])
