"""Real HTTP session contexts, profile revisions, migration and shared metadata."""
import json
import tempfile
import sqlite3
import urllib.request
import urllib.error
from pathlib import Path
import unittest
from jsonschema import Draft202012Validator
import test_api_contracts as base
from sbc.core import Store
from sbc.contracts_v2 import contract_v2

class ProfileTests(base.ContractTests):
    test_live_responses=None
    test_authenticated_contract_discovery=None
    test_error_responses=None
    test_exported_contracts_and_schema_validity=None

    def setUp(self):
        super().setUp();self.poller.once()

    def call(self,path='/api/v2/configuration',body=None,method='GET',profile=None,cookie=None,tag=None,status=200,token=base.TOKEN):
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
        if profile is not None:headers['X-Dashboard-Profile']=profile
        if cookie is not None:headers['Cookie']=cookie
        if tag:headers['If-Match']=tag
        request=urllib.request.Request(self.dashboard.url+path,data=json.dumps(body).encode() if body is not None else None,method=method,headers=headers)
        try:response=urllib.request.urlopen(request)
        except urllib.error.HTTPError as error:response=error
        self.assertEqual(response.status,status);result=json.load(response);return result,response.headers

    def create(self,name):return self.call('/api/v2/profiles',{'name':name},'POST',status=201)[0]['id']
    def save(self,profile,title,unit='celsius'):
        doc,h=self.call(profile=profile);body={k:doc[k] for k in ('locations','devices','dashboard')};body['dashboard'].update(title=title,temperature_unit=unit)
        return self.call(body=body,method='PUT',profile=profile,tag=h['ETag'])

    def test_migration_defaults_and_restart_preserve_admin(self):
        with tempfile.TemporaryDirectory() as directory:
            path=directory+'/old.sqlite3';store=Store(path)
            doc=store.configuration_document();doc['dashboard']['title']='Existing home'
            store.replace_configuration({k:doc[k] for k in ('locations','devices','dashboard')},store.configuration_etag())
            expected=store.configuration_document();store.close()
            with sqlite3.connect(path) as db:db.execute('DROP TABLE user_profiles')
            store=Store(path);self.assertEqual(store.configuration_document(),expected)
            other=store.save_profile({'name':'Mark'})['id'];self.assertEqual(store.configuration_document(other)['dashboard']['widgets'],[])
            store.close();store=Store(path)
            self.assertEqual(store.configuration_document(),expected);self.assertEqual(len(store.profiles_document()['profiles']),2);store.close()

    def test_cookie_resolution_header_precedence_and_authentication(self):
        a=self.create('Alice');self.save(a,'Alice home','fahrenheit')
        doc,h=self.call(cookie='dashboard_profile='+a);self.assertEqual(doc['dashboard']['title'],'Alice home');self.assertEqual(h['X-Dashboard-Profile'],a)
        self.assertEqual(self.call(profile='admin',cookie='dashboard_profile='+a)[0]['dashboard']['title'],'Home')
        for cookie in ['','dashboard_profile=garbage','dashboard_profile=%ZZ','dashboard_profile=p-'+'f'*24,'dashboard_profile="unterminated']:
            self.assertEqual(self.call(cookie=cookie)[1]['X-Dashboard-Profile'],'admin')
        self.call('/api/v2/profiles',token='bad',status=401)
        self.call(body={'name':'Bad'},path='/api/v2/profiles',method='POST',token='bad',status=401)
        listing,_=self.call('/api/v2/profiles',cookie='dashboard_profile='+a)
        doc=contract_v2();Draft202012Validator(dict(doc['components']['schemas']['UserProfiles'],components=doc['components'])).validate(listing)

    def test_independent_sessions_and_scoped_revisions(self):
        a=self.create('Alice');b=self.create('Bob');admin=self.call()[0]
        original_a,ha=self.call(profile=a);original_b,hb=self.call(profile=b)
        body={k:original_a[k] for k in ('locations','devices','dashboard')};body['dashboard']['title']='Alice home'
        self.call(body=body,method='PUT',profile=a,tag=ha['ETag'])
        bodyb={k:original_b[k] for k in ('locations','devices','dashboard')};bodyb['dashboard']['temperature_unit']='fahrenheit'
        self.call(body=bodyb,method='PUT',profile=b,tag=hb['ETag'])
        self.assertEqual(self.call()[0],admin)
        self.assertEqual(self.call(profile=a)[0]['dashboard']['temperature_unit'],'celsius')
        self.assertEqual(self.call(profile=b)[0]['dashboard']['title'],'Home')
        self.call(body=bodyb,method='PUT',profile=a,tag=hb['ETag'],status=412)
        self.call(body=body,method='PUT',profile=a,tag=ha['ETag'],status=412)
        bob_tag=self.call(profile=b)[1]['ETag']
        self.save('admin','Admin only')
        self.assertEqual(self.call(profile=b)[1]['ETag'],bob_tag)
        self.assertEqual(self.call(profile=b)[0]['dashboard']['temperature_unit'],'fahrenheit')

    def test_shared_changes_invalidate_all_contexts_but_history_is_shared(self):
        a=self.create('Alice');b=self.create('Bob');before,h=self.call(profile=b)
        self.store.save_location('Shared room')
        for profile in ['admin',a,b]:self.assertEqual(self.call(profile=profile)[0]['locations'][0]['name'],'Shared room')
        self.call(body={k:before[k] for k in ('locations','devices','dashboard')},method='PUT',profile=b,tag=h['ETag'],status=412)
        self.assertEqual(self.call('/api/v2/devices',profile=a)[0],self.call('/api/v2/devices',profile=b)[0])
        self.save(a,'Alice')
        self.assertEqual(self.store.db.execute('select count(*) from measurements').fetchone()[0],3)

    def test_deleted_profile_never_writes_into_admin(self):
        a=self.create('Alice');doc,h=self.call(profile=a);admin=self.call()[0]
        self.call('/api/v2/profiles/'+a,method='DELETE')
        self.assertEqual(self.call(profile=a)[1]['X-Dashboard-Profile'],'admin')
        self.call(body={k:doc[k] for k in ('locations','devices','dashboard')},method='PUT',profile=a,tag=h['ETag'],status=409)
        self.assertEqual(self.call()[0],admin)

    def test_management_validation_limits_and_stable_ids(self):
        a=self.create('Alice')
        for name in ['alice','Ａｌｉｃｅ','Admin']:self.call('/api/v2/profiles',{'name':name},'POST',status=409)
        for body in [{'name':''},{'name':'x'*81},{'name':'bad\nname'},{'name':5},{'name':'Okay','password':'bad'}]:self.call('/api/v2/profiles',body,'POST',status=422)
        doc,_=self.call('/api/v2/profiles/'+a,{'name':'Renamed'},'PUT');self.assertEqual(doc['id'],a)
        for method,body in [('PUT',{'name':'Root'}),('DELETE',None)]:self.call('/api/v2/profiles/admin',body,method,status=409)
        for i in range(18):self.create('Other '+str(i))
        self.call('/api/v2/profiles',{'name':'Too many'},'POST',status=409)
