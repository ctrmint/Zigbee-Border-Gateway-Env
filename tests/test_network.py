"""Gateway rediscovery authentication, identity persistence and uncertain writes."""
import hashlib
import hmac
import json
import tempfile
import unittest
import urllib.error
from unittest.mock import patch
from sbc.core import Gateway, Store, Poller
from sbc.network import discovery_response

ID='b8f86262ff08';TOKEN='network-test-token'

def packet(nonce='a'*32,identity=ID,port=80,token=TOKEN):
    proof=hmac.new(token.encode(),f'{nonce}|{identity}|{port}'.encode(),hashlib.sha256).hexdigest()
    return json.dumps(dict(nonce=nonce,gateway_id=identity,port=port,proof=proof)).encode()

class NetworkTests(unittest.TestCase):
    def test_discovery_requires_nonce_token_identity_and_private_ipv4(self):
        self.assertEqual(discovery_response(packet(),'a'*32,ID,TOKEN,'10.81.1.42'),'http://10.81.1.42:80')
        for p,n,i,t,a in [(b'bad','a'*32,ID,TOKEN,'10.0.0.2'),(packet(),'b'*32,ID,TOKEN,'10.0.0.2'),
            (packet(),'a'*32,'000000000000',TOKEN,'10.0.0.2'),(packet(),'a'*32,ID,'wrong','10.0.0.2'),
            (packet(),'a'*32,ID,TOKEN,'8.8.8.8'),(packet(),'a'*32,ID,TOKEN,'::1'),
            (packet(port=0),'a'*32,ID,TOKEN,'10.0.0.2')]:
            self.assertIsNone(discovery_response(p,n,i,t,a))

    def test_binding_survives_pi_restart_and_changes_do_not_write_each_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp+'/n.sqlite3');g=Gateway('http://10.0.0.1',TOKEN);Poller(g,store)
            with patch.object(g,'_http',return_value={'gateway_id':ID}):g.request('/api/v1/health')
            before=store.db.total_changes
            with patch.object(g,'_http',return_value={'gateway_id':ID}):
                for _ in range(10):g.request('/api/v1/health')
            self.assertEqual(before,store.db.total_changes)
            g.url='http://10.0.0.2';g._remember(ID);store.close()
            store=Store(tmp+'/n.sqlite3');other=Gateway('http://10.0.0.1',TOKEN);Poller(other,store)
            self.assertEqual((other.identity,other.url),(ID,'http://10.0.0.2'))
            wrong=Gateway('http://10.0.0.1','different token');Poller(wrong,store);self.assertIsNone(wrong.identity)
            store.close()

    def test_get_recovers_after_address_change_with_authenticated_health(self):
        g=Gateway('http://10.0.0.1',TOKEN);g._remember(ID)
        health={'gateway_id':ID,'boot_id':'same-boot'}
        with patch.object(g,'_http',side_effect=[urllib.error.URLError('offline'),health]),patch.object(g,'_discover',return_value='http://10.0.0.2'):
            self.assertEqual(g.request('/api/v1/health'),health)
        self.assertEqual(g.url,'http://10.0.0.2')
        with patch.object(g,'_http',side_effect=[{'gateway_id':'000000000000'},health]),patch.object(g,'_discover',return_value='http://10.0.0.3'):
            self.assertEqual(g.request('/api/v1/health'),health)
        self.assertEqual(g.url,'http://10.0.0.3')

    def test_unrelated_device_rejected_and_uncertain_post_not_repeated(self):
        g=Gateway('http://10.0.0.1',TOKEN);g._remember(ID)
        with patch.object(g,'_http',side_effect=[urllib.error.URLError('offline'),{'gateway_id':'000000000000'}]),patch.object(g,'_discover',return_value='http://10.0.0.2'):
            with self.assertRaises(ValueError):g.request('/api/v1/health')
        self.assertEqual(g.url,'http://10.0.0.1')
        with patch.object(g,'_http',side_effect=[urllib.error.URLError('uncertain'),{'gateway_id':ID}]) as call,patch.object(g,'_discover',return_value='http://10.0.0.2'):
            with self.assertRaises(urllib.error.URLError):g.request('/api/v1/commands',{'op':'on_off'})
            self.assertEqual(call.call_count,2)
            self.assertIsNone(call.call_args.args[1] if len(call.call_args.args)>1 else None)
        self.assertEqual(g.url,'http://10.0.0.2')

    def test_initial_authentication_failure_not_retried_and_wrong_host_can_rediscover(self):
        g=Gateway('http://10.0.0.1',TOKEN)
        unauthorized=urllib.error.HTTPError(g.url,401,'unauthorized',{},None)
        with patch.object(g,'_http',side_effect=unauthorized),patch.object(g,'_discover') as discover:
            with self.assertRaises(urllib.error.HTTPError):g.request('/api/v1/health')
            discover.assert_not_called()
        g._remember(ID)
        with patch.object(g,'_http',side_effect=[unauthorized,{'gateway_id':ID}]),patch.object(g,'_discover',return_value='http://10.0.0.2'):
            self.assertEqual(g.request('/api/v1/health')['gateway_id'],ID)

    def test_unknown_identity_never_broadcasts_and_discovery_is_rate_limited(self):
        g=Gateway('http://10.0.0.1',TOKEN)
        with patch('sbc.network.socket.socket') as sock:self.assertIsNone(g._discover());sock.assert_not_called()
        g._remember(ID);g._next_discovery=__import__('time').monotonic()+30
        with patch('sbc.network.socket.socket') as sock:self.assertIsNone(g._discover());sock.assert_not_called()

    def test_live_discovery_request_is_authenticated_and_response_pinned(self):
        g=Gateway('http://10.81.1.42',TOKEN);g.identity=ID
        class Datagram:
            sent=[]
            def __enter__(self):return self
            def __exit__(self,*args):pass
            def setsockopt(self,*args):pass
            def settimeout(self,*args):pass
            def sendto(self,payload,peer):self.sent.append(json.loads(payload))
            def recvfrom(self,size):return packet(nonce=self.sent[-1]['nonce']),('10.81.1.42',39128)
        d=Datagram()
        with patch('sbc.network.socket.socket',return_value=d):self.assertEqual(g._discover(),'http://10.81.1.42:80')
        request=d.sent[-1]
        self.assertEqual(request['proof'],hmac.new(TOKEN.encode(),('discover|'+request['nonce']).encode(),hashlib.sha256).hexdigest())
        self.assertNotIn(TOKEN,json.dumps(request))
        with patch('sbc.network.socket.socket') as sock:self.assertIsNone(g._discover());sock.assert_not_called()

    def test_buffered_measurements_keep_original_age_after_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp+'/ages.sqlite3');ieee='0000000000000001'
            event=dict(type='attribute',seq=1,ieee=ieee,nwk=1,endpoint=1,cluster=1026,attribute=0,data_type=41,raw=1800,rssi=-82,origin='report',uptime_ms=800000)
            class Buffered:
                def request(self,path):
                    if path.endswith('health'):return dict(boot_id='buffered',uptime_ms=8000000,ready=True)
                    if '/events?' in path:return dict(boot_id='buffered',events=[event],next_seq=1,latest_seq=1,gap=False)
                    return dict(boot_id='buffered',devices=[dict(ieee=ieee,nwk=1,active=True,endpoints={'1':{'input_clusters':[1026]}})])
            p=Poller(Buffered(),store)
            with patch('time.time',return_value=1700000000):
                p.once();view=store.device_views()['devices'][0]
                self.assertEqual(view['measurements'][0]['quality'],'stale')
                self.assertEqual(view['signal']['quality'],'stale')
                self.assertEqual(view['measurements'][0]['received_at'],1699992800)
            self.assertEqual(store.db.execute('select received from measurements').fetchone()[0],1699992800)
            self.assertEqual(store.db.execute('select received from events').fetchone()[0],1700000000)
            store.close()
