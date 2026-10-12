import tempfile
import threading
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from sbc.core import Store, Gateway, Poller, validate_command, normalize
from sbc.simulator import Simulation, make_handler as sim_handler
from sbc.app import make_handler
TOKEN='a'*64
class SystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name+'/test.sqlite3');self.sim=Simulation()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),sim_handler(self.sim,TOKEN))
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.gateway=Gateway('http://127.0.0.1:'+str(self.server.server_port),TOKEN);self.poller=Poller(self.gateway,self.store)
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.store.close();self.tmp.cleanup()
    def test_end_to_end_and_deduplication(self):
        self.poller.once();ds=self.store.snapshot();self.assertEqual(len(ds),2)
        self.assertEqual(ds[1]['attributes']['1:1026:0']['value'],20.5)
        self.assertEqual(ds[1]['endpoints']['1']['input_clusters'],[1026,1029])
        self.gateway.request('/api/v1/commands',{'op':'on_off','ieee':ds[0]['ieee'],'endpoint':1,'state':True});self.poller.once()
        self.assertIs(self.store.snapshot()[0]['attributes']['1:6:0']['value'],True)
        before=len(self.store.history());self.poller.once();self.assertEqual(len(self.store.history()),before)
    def test_restart_and_gap(self):
        self.poller.once();self.sim.boot='newboot';self.sim.events=[];self.sim.seq=0;self.sim.measure()
        self.poller.once();self.assertEqual(self.store.cursor()[0],'newboot')
        for _ in range(80):self.sim.measure()
        self.poller.once();self.assertTrue(self.poller.status['gap'])
    def test_authentication(self):
        with self.assertRaises(urllib.error.HTTPError) as e:Gateway(self.gateway.url,'wrong').request('/api/v1/devices')
        self.assertEqual(e.exception.code,401)
    def test_invalid_commands(self):
        for c in [{},{'op':[]},{'op':{}},{'op':None},{'op':1},
                  {'op':'permit_join','seconds':181},{'op':'permit_join','seconds':True},
                  {'op':'on_off','ieee':'0'*16,'endpoint':1,'state':1},
                  {'op':'read','ieee':'0'*16,'endpoint':0,'cluster':0,'attribute':0},
                  {'op':'permit_join','seconds':60,'other':1}]:
            with self.assertRaises(ValueError):validate_command(c)
    def test_zcl_sentinels(self):
        self.assertEqual(normalize(0x0402,0,0x29,-32768),(None,None));self.assertEqual(normalize(0x0405,0,0x21,65535),(None,None))
        self.assertEqual(normalize(0x0402,0,0x29,-525),(-5.25,'°C'));self.assertEqual(normalize(6,0,0x10,255),(None,None))
    def test_dashboard_proxy_and_offline(self):
        self.poller.once();server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(self.store,self.poller,self.gateway,TOKEN))
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url='http://127.0.0.1:'+str(server.server_port)
        try:
            with urllib.request.urlopen(url+'/') as r:self.assertIn(b'Zigbee house gateway',r.read())
            with self.assertRaises(urllib.error.HTTPError) as e:urllib.request.urlopen(url+'/api/v1/state')
            self.assertEqual(e.exception.code,401);dashboard=Gateway(url,TOKEN)
            for op in ([], {}):
                with self.assertRaises(urllib.error.HTTPError) as e:
                    dashboard.request('/api/v1/commands', {'op':op})
                self.assertEqual(e.exception.code,400)
            self.assertEqual(len(dashboard.request('/api/v1/state')['devices']),2);self.poller.status['connected']=False
            with self.assertRaises(urllib.error.HTTPError) as e:dashboard.request('/api/v1/commands',{'op':'permit_join','seconds':60})
            self.assertEqual(e.exception.code,503)
        finally:server.shutdown();server.server_close();thread.join()
    def test_simulator_rejects_malformed_op(self):
        for op in ([], {}):
            with self.assertRaises(urllib.error.HTTPError) as e:
                self.gateway.request('/api/v1/commands', {'op':op})
            self.assertEqual(e.exception.code,400)
    def test_registry_wins_over_historical_events(self):
        # The initial announcement and reports still have the old address.
        # Simulate membership changes whose events were missed.
        self.sim.devices[0].update(nwk=0x3456, active=False)
        self.poller.once()
        d=self.store.snapshot()[0]
        self.assertEqual(d['nwk'],0x3456)
        self.assertFalse(d['active'])
        self.assertIn('1',d['endpoints'])
        self.assertIn('1:6:0',d['attributes'])
        # A historical leave must also not undo a current rejoin.
        self.sim.emit(dict(self.sim.devices[0],type='leave'))
        self.sim.devices[0].update(nwk=0x4567,active=True)
        self.poller.once()
        d=self.store.snapshot()[0]
        self.assertEqual(d['nwk'],0x4567)
        self.assertTrue(d['active'])
    def test_restart_during_registry_fetch_does_not_commit(self):
        self.poller.once()
        cursor=self.store.cursor(); snapshot=self.store.snapshot(); history=self.store.history()
        self.sim.measure()
        gateway=self.gateway
        class RestartingGateway:
            def request(inner,path):
                if path=='/api/v1/devices':
                    self.sim.boot='restarted'
                    self.sim.devices[0]['active']=False
                return gateway.request(path)
        self.poller.gateway=RestartingGateway()
        with self.assertRaises(RuntimeError):self.poller.once()
        self.assertEqual(self.store.cursor(),cursor)
        self.assertEqual(self.store.snapshot(),snapshot)
        self.assertEqual(self.store.history(),history)
    def test_persistent_registry_and_cursor(self):
        self.poller.once();cursor=self.store.cursor();self.store.close();self.store=Store(self.tmp.name+'/test.sqlite3')
        self.assertEqual(self.store.cursor(),cursor);self.assertEqual(len(self.store.snapshot()),2)
if __name__=='__main__':unittest.main()
