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
        self.on = False
        for d in self.devices:
            self.emit(dict(d, type="announce"))
            self.emit(dict(d, type="endpoint", endpoint=1, ok=True, profile_id=0x104,
                device_id=0, input_clusters=[0x0006] if d == self.devices[0] else [0x0402,0x0405], output_clusters=[]))
        self.measure()
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
    def command(self, c):
        validate_command(c)
        with self.lock:
            if c["op"] == "permit_join":
                self.join_until = time.time() + c["seconds"]
            else:
                if c["ieee"] not in {d["ieee"] for d in self.devices}:
                    raise ValueError("unknown device")
                if c['op'] in ('bind','configure_reporting','read_reporting'):
                    d=next(d for d in self.devices if d['ieee']==c['ieee'])
                    key=(c['ieee'],c['endpoint'],c['cluster'])
                    status=self.reporting_failures.get((c['op'],c['cluster']),0)
                    e=dict(d,type='commissioning',endpoint=c['endpoint'],cluster=c['cluster'],attribute=0,
                        request_id=c['request_id'],operation=c['op'],phase='response',status=status,tsn=42)
                    if c['op']=='configure_reporting' and status==0:self.reporting[key]={k:c[k] for k in ('min_interval','max_interval','reportable_change')}
                    if c['op']=='read_reporting' and status==0:
                        if key not in self.reporting:e['status']=0x8b
                        else:e.update(self.reporting[key],data_type=0x29 if c['cluster']==1026 else 0x21)
                    self.emit(e)
                elif c["op"] == "on_off":
                    if c["ieee"] != self.devices[0]["ieee"] or c["endpoint"] != 1:
                        raise ValueError("not an on/off device")
                    self.on = c["state"]
                    self.attr(0, 6, 0x10, int(self.on))
                elif c["op"] == "read":
                    index=next(i for i,d in enumerate(self.devices) if d['ieee']==c['ieee'])
                    if c['cluster']==0 and c['attribute'] in (4,5):self.attr(index,0,0x42,'SONOFF' if c['attribute']==4 else 'SNZB-02WD',c['attribute'],origin='read_response')
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
                    obj={"reporting_commissioning":True,"mode":"simulator","boot_id":sim.boot,"ready":True,"latest_seq":sim.seq,
                         "join_seconds":max(0,int(sim.join_until-time.time())),"dropped_events":0}
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
