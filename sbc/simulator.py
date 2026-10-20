"""Explicitly simulated Zigbee gateway; no physical radio is used."""
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
import hmac
from .core import validate_command

class Simulation:
    def __init__(self):
        self.boot = secrets.token_hex(8)
        self.lock = threading.RLock()
        self.events = []
        self.seq = 0
        self.join_until = 0
        self.devices = [{"ieee": "00124b0000000001", "nwk": 0x1234, "active": True},
                        {"ieee": "00124b0000000002", "nwk": 0x2345, "active": True}]
        self.reporting = {}
        self.reporting_failures = {}
        self.display_values={}
        self.display_failures={}
        self.plug_values={}
        self.plug_failures={}
        self.clock=None
        self.on = False
        for d in self.devices:
            self.emit(dict(d, type="announce"))
            self.emit(dict(d, type="endpoint", endpoint=1, ok=True, profile_id=0x104,
                device_id=0, input_clusters=[0x0006] if d == self.devices[0] else [0x0402,0x0405], output_clusters=[]))
        self.measure()
    def add_snzb02ul(self, voltage=False, vendor_cluster=True, on_off=True):
        """Synthetic reference fixture, not a capture from a physical SNZB-02UL."""
        d={'ieee':'00124b0000000014','nwk':0x3414,'active':True};self.devices.append(d)
        self.emit(dict(d,type='announce'))
        clusters=[0,1,3,1026,1029,32]+([64529] if vendor_cluster else [])+([6] if on_off else [])
        self.emit(dict(d,type='endpoint',endpoint=1,ok=True,profile_id=260,device_id=770,input_clusters=clusters,output_clusters=[10,25]))
        i=len(self.devices)-1
        for attr,raw in [(4,'SONOFF'),(5,'SNZB-02UL'),(0x4000,'synthetic-1.0')]:self.attr(i,0,0x42,raw,attr,origin='read_response')
        self.attr(i,1026,0x29,2150);self.attr(i,1029,0x21,4820);self.attr(i,1,0x20,160,33)
        if voltage:self.attr(i,1,0x20,30,32)
        self.display_values.update({(d['ieee'],attr):value for attr,value in [(3,2600),(4,1800),(5,3000),(6,6000),(7,0),(0x2003,0),(0x2004,0)]})
        return d
    def emit(self, e):
        with self.lock:
            self.seq += 1
            self.events.append(dict(e, seq=self.seq, uptime_ms=int(time.monotonic()*1000)))
            self.events = self.events[-64:]
    def attr(self, index, cluster, dtype, raw, aid=0, origin="report"):
        self.emit(dict(self.devices[index], type="attribute", endpoint=1, cluster=cluster,
            attribute=aid, data_type=dtype, raw=raw, rssi=-50, origin=origin))
    def measure(self):
        self.attr(0, 6, 0x10, int(self.on))
        self.attr(1, 0x0402, 0x29, 2050)
        self.attr(1, 0x0405, 0x21, 4800)
    def add_s60zbtpg(self):
        """Synthetic fixture only; never added to the hardware registry."""
        from .plugs import READS
        d={'ieee':'00124b0000000027','nwk':0x3427,'active':True};self.devices.append(d);i=len(self.devices)-1
        self.emit(dict(d,type='announce',capability=0x8e))
        self.emit(dict(d,type='endpoint',endpoint=1,ok=True,profile_id=260,device_id=0x51,input_clusters=[0,3,4,5,6,1794,64529],output_clusters=[10,25]))
        for a,v in [(4,'SONOFF'),(5,'S60ZBTPG'),(0x4000,'synthetic-1.0')]:self.attr(i,0,0x42,v,a,origin='read_response')
        values={(6,0):1,(6,0x4003):255,(64529,1):1,(64529,0x7007):1,(64529,0x7003):'040b010001c8320000a0973100',
            (1794,768):0,(1794,769):1,(1794,770):1000,(1794,0):123456789012,(64529,0x7004):1000,(64529,0x7005):230000,(64529,0x7006):230000,(64529,0x7009):1500,(64529,0x700a):25000,(64529,0x700b):2000}
        from .plugs import protection
        values[(64529,0x7003)]=protection({'max_current':13,'max_power':3250})
        for key,raw in values.items():
            self.plug_values[(d['ieee'],*key)]=raw
            if key==(64529,0x7003):self.emit(dict(d,type='attribute',endpoint=1,cluster=key[0],attribute=key[1],data_type=0x42,raw_hex=raw,rssi=-50,origin='report'))
            else:self.attr(i,key[0],READS[key],raw,key[1])
        return d
    def plug_command(self,c):
        from .plugs import validate_command,READS,REPORTS
        validate_command(c)
        d=next((d for d in self.devices if d['ieee']==c['ieee']),None)
        if d is None or c['ieee']!='00124b0000000027':raise ValueError('Not an identified S60ZBTPG')
        key=(c['ieee'],c['cluster'],c['attribute']);op=c['op'];status=self.plug_failures.get((op,c['cluster'],c['attribute']),0)
        e=dict(d,type='commissioning',endpoint=c['endpoint'],cluster=c['cluster'],attribute=c['attribute'],request_id=c['request_id'],operation=op,phase='response',status=status,tsn=44)
        if status==0:
            if op in ('plug_write','plug_relay'):self.plug_values[key]=c.get('value',c.get('payload'))
            if op=='plug_read':
                raw=self.plug_values[key];e['data_type']=READS[key[1:]]
                if key[1:]==(64529,0x7003):e['raw_hex']=raw;self.emit(dict(d,type='attribute',endpoint=c['endpoint'],cluster=key[1],attribute=key[2],data_type=0x42,raw_hex=raw,rssi=-50,origin='read_response'))
                else:e['raw']=raw;self.attr(self.devices.index(d),key[1],e['data_type'],raw,key[2],origin='read_response')
            if op=='plug_configure':self.reporting[key]=REPORTS[key[1:]]
            if op=='plug_read_reporting':
                spec=self.reporting.get(key)
                if spec:e.update(zip(('data_type','min_interval','max_interval','reportable_change'),spec))
                else:e['status']=0x8b
        self.emit(e);return {'accepted':True,'stack_result':0}
    def command(self, c):
        if isinstance(c,dict) and isinstance(c.get('op'),str) and c['op'].startswith('plug_'):
            with self.lock:return self.plug_command(c)
        validate_command(c)
        with self.lock:
            if c['op']=='sync_clock':
                self.clock=dict(c,synced=time.monotonic());return {'accepted':True,'stack_result':0}
            if c["op"] == "permit_join":
                self.join_until = time.time() + c["seconds"]
            else:
                if c["ieee"] not in {d["ieee"] for d in self.devices}:
                    raise ValueError("unknown device")
                if c['op'] in ('write_display','read_display'):
                    from .sensors import DISPLAY_FIELDS
                    d=next(d for d in self.devices if d['ieee']==c['ieee']);attr=c['attribute']
                    status=self.display_failures.get((c['op'],attr),0)
                    e=dict(d,type='commissioning',endpoint=c['endpoint'],cluster=64529,attribute=attr,request_id=c['request_id'],operation=c['op'],phase='response',status=status,tsn=43)
                    if (d['ieee'],attr) not in self.display_values:e['status']=0x86
                    elif status==0:
                        dtype=next(v[1] for v in DISPLAY_FIELDS.values() if v[0]==attr)
                        if c['op']=='write_display':self.display_values[(d['ieee'],attr)]=c['value']
                        else:
                            e.update(raw=self.display_values[(d['ieee'],attr)],data_type=dtype)
                            self.attr(self.devices.index(d),64529,dtype,e['raw'],attr,origin='read_response')
                    self.emit(e)
                elif c['op'] in ('bind','configure_reporting','read_reporting'):
                    d=next(d for d in self.devices if d['ieee']==c['ieee'])
                    key=(c['ieee'],c['endpoint'],c['cluster'])
                    status=self.reporting_failures.get((c['op'],c['cluster']),0)
                    e=dict(d,type='commissioning',endpoint=c['endpoint'],cluster=c['cluster'],attribute=c.get('attribute',0),
                        request_id=c['request_id'],operation=c['op'],phase='response',status=status,tsn=42)
                    if c['op']=='configure_reporting' and status==0:self.reporting[key]={k:c[k] for k in ('min_interval','max_interval','reportable_change')}
                    if c['op']=='read_reporting' and status==0:
                        if key not in self.reporting:e['status']=0x8b
                        else:e.update(self.reporting[key],data_type=0x29 if c['cluster']==1026 else 0x20 if c['cluster']==1 else 0x21)
                    self.emit(e)
                elif c["op"] == "on_off":
                    if c["ieee"] != self.devices[0]["ieee"] or c["endpoint"] != 1:
                        raise ValueError("not an on/off device")
                    self.on = c["state"]
                    self.attr(0, 6, 0x10, int(self.on))
                elif c["op"] == "read":
                    index=next(i for i,d in enumerate(self.devices) if d['ieee']==c['ieee'])
                    if c['ieee']=='00124b0000000014':
                        attributes={(0,4):(0x42,'SONOFF'),(0,5):(0x42,'SNZB-02UL'),(0,0x4000):(0x42,'synthetic-1.0')}
                        for event in self.events:
                            if event.get('ieee')==c['ieee'] and event.get('type')=='attribute':attributes[(event['cluster'],event['attribute'])]=(event['data_type'],event.get('raw'))
                        value=attributes.get((c['cluster'],c['attribute']))
                        if value:self.attr(index,c['cluster'],*value,c['attribute'],origin='read_response')
                        else:self.emit(dict(self.devices[index],type='zcl_response',status=0x86,tsn=42))
                    elif c['ieee']=='00124b0000000027' and c['cluster']==0 and c['attribute'] in (4,5):self.attr(index,0,0x42,'SONOFF' if c['attribute']==4 else 'S60ZBTPG',c['attribute'],origin='read_response')
                    elif c['cluster']==0 and c['attribute'] in (4,5):self.attr(index,0,0x42,'SONOFF' if c['attribute']==4 else 'SNZB-02WD',c['attribute'],origin='read_response')
                    else:self.attr(index,c['cluster'],0x29 if c['cluster']==1026 else 0x21 if c['cluster']==1029 else 0x10,2050 if c['cluster']==1026 else 4800 if c['cluster']==1029 else int(self.on),c['attribute'],origin='read_response')
                elif c["op"] == "discover":
                    index = next(i for i,d in enumerate(self.devices) if d["ieee"]==c["ieee"])
                    self.emit(dict(self.devices[index], type="endpoint", endpoint=1, ok=True, profile_id=0x104,
                        device_id=0, input_clusters=[6] if index==0 else [0x0402,0x0405], output_clusters=[]))
            return {"accepted": True, "stack_result": 0}

def make_handler(sim, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def send(self, code, obj):
            data=json.dumps(obj).encode();self.send_response(code)
            self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(data)))
            self.end_headers();self.wfile.write(data)
        def auth(self):
            return hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer "+token)
        def do_GET(self):
            if not self.auth(): return self.send(401,{"error":"token required"})
            p=urlparse(self.path)
            with sim.lock:
                if p.path == "/api/v1/health":
                    obj={"plug_extensions":True,"sensor_extensions":True,"time_server_valid":bool(sim.clock and time.monotonic()-sim.clock["synced"]<900),"reporting_commissioning":True,"mode":"simulator","boot_id":sim.boot,"ready":True,"latest_seq":sim.seq,"uptime_ms":int(time.monotonic()*1000),"channel":20,"pan_id":0x1a62,
                         "join_seconds":max(0,int(sim.join_until-time.time())),"dropped_events":0}
                elif p.path == "/api/v1/radio":
                    obj={"boot_id":sim.boot,"mode":"simulator","ready":True,"uptime_ms":int(time.monotonic()*1000),
                        "channel":20,"pan_id":0x1a62,"scope":"simulated_coordinator_local_tables",
                        "neighbor_source":"synthetic_fixture_not_radio_observation",
                        "route_source":"synthetic_fixture_not_radio_observation",
                        "neighbors":[{"ieee":d["ieee"],"nwk":d["nwk"],"device_type":2,"depth":1,"rx_on_when_idle":False,
                            "relationship":1,"lqi":180-i*12,"rssi_dbm":-48-i*7,"outgoing_cost":2+i,"age_periods":0,
                            "device_timeout_seconds":0,"timeout_ms":0} for i,d in enumerate(sim.devices[:2])],
                        "routes":[],"route_records":[]}
                elif p.path == "/api/v1/devices": obj={"boot_id":sim.boot,"devices":sim.devices}
                elif p.path == "/api/v1/events":
                    try: after=int(parse_qs(p.query).get("after",[0])[0])
                    except ValueError: return self.send(400,{"error":"invalid cursor"})
                    oldest=sim.events[0]["seq"] if sim.events else 1
                    gap=after+1<oldest or after>sim.seq
                    if gap: after=oldest-1
                    batch=[e for e in sim.events if e["seq"]>after][:16]
                    obj={"boot_id":sim.boot,"gap":gap,"events":batch,
                         "next_seq":batch[-1]["seq"] if batch else after,"latest_seq":sim.seq}
                else: return self.send(404,{"error":"not found"})
                self.send(200,obj)
        def do_POST(self):
            if not self.auth(): return self.send(401,{"error":"token required"})
            if self.path!="/api/v1/commands": return self.send(404,{"error":"not found"})
            try:
                n=int(self.headers.get("Content-Length",0))
                if not 0<n<=512: raise ValueError("body size")
                obj=sim.command(json.loads(self.rfile.read(n)))
            except (ValueError,UnicodeError): return self.send(400,{"error":"invalid command"})
            self.send(202,obj)
    return Handler

def main():
    token=os.environ.get("GATEWAY_TOKEN","")
    if len(token)<32: raise SystemExit("Set GATEWAY_TOKEN to at least 32 characters")
    server=ThreadingHTTPServer(("127.0.0.1",int(os.environ.get("SIM_PORT","8081"))),make_handler(Simulation(),token))
    print("SIMULATOR: no radio connected",flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
if __name__=="__main__": main()
