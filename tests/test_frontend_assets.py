"""Production bundle delivery and preview boundaries over real HTTP."""
import importlib.util
from pathlib import Path
import urllib.request
import urllib.error
import test_api_contracts as base


class FrontendAssetsTests(base.ContractTests):
    test_live_responses=None
    test_authenticated_contract_discovery=None
    test_error_responses=None
    test_exported_contracts_and_schema_validity=None

    def test_bundle_served_with_scoped_csp_and_path_bounds(self):
        with urllib.request.urlopen(self.dashboard.url+'/') as response:
            html=response.read().decode();policy=response.headers['Content-Security-Policy']
        self.assertIn('/assets/',html)
        self.assertIn("script-src 'self'",policy)
        self.assertNotIn("script-src 'self' 'unsafe-inline'",policy)
        with urllib.request.urlopen(self.dashboard.url+'/') as response:
            self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])
        for path in ('/assets/../../../../.env','/assets/missing.js','/app.js','/style.css'):
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(self.dashboard.url+path)
            self.assertEqual(caught.exception.code,404)

    def test_preview_disables_device_and_profile_actions(self):
        path=Path(__file__).resolve().parents[1]/'scripts/preview_dashboard.py'
        spec=importlib.util.spec_from_file_location('preview_dashboard',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        preview=self.serve(module.preview_handler(self.store,base.TOKEN,self.dashboard.url,self.dashboard.url))
        for method,path in (('POST','/api/v1/commands'),('POST','/api/v2/plugs'),('POST','/api/v2/profiles'),('DELETE','/api/v2/profiles/admin'),('PUT','/api/v1/locations')):
            req=urllib.request.Request(preview.url+path,data=b'{}',method=method,headers={'Authorization':'Bearer '+base.TOKEN})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code,405)
        for path in ('/api/v1/state','/api/v2/devices','/api/v2/history?limit=500'):
            req=urllib.request.Request(preview.url+path)
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code,401)

    def test_preview_forwards_only_authenticated_bounded_history_get(self):
        import time,json
        self.poller.once()
        path=Path(__file__).resolve().parents[1]/'scripts/preview_dashboard.py'
        spec=importlib.util.spec_from_file_location('preview_dashboard',path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        preview=self.serve(module.preview_handler(self.store,base.TOKEN,self.dashboard.url,self.dashboard.url))
        query=urllib.parse.urlencode(dict(ieee=self.sim.devices[1]['ieee'],endpoint=1,cluster=1026,attribute=0,limit=500,**{'from':time.time()-3600,'to':time.time()}))
        req=urllib.request.Request(preview.url+'/api/v2/history?'+query,headers={'Authorization':'Bearer '+base.TOKEN})
        with urllib.request.urlopen(req) as response:result=json.load(response)
        self.assertTrue(result['items']);self.assertLessEqual(len(result['items']),500)
