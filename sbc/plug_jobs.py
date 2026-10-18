"""Durable plug jobs. Load-changing commands are submitted once, never replayed."""
import json
import re
import time
import uuid
from .dashboard import DashboardError
from . import plugs

ACTIVE={'queued','sending','waiting'}
class PlugStore:
    def _init_plugs(self):
        self.db.executescript('''CREATE TABLE IF NOT EXISTS plug_jobs(id TEXT PRIMARY KEY,ieee TEXT NOT NULL REFERENCES devices(ieee),data TEXT NOT NULL);
          CREATE INDEX IF NOT EXISTS plug_job_device ON plug_jobs(ieee);
          CREATE TABLE IF NOT EXISTS plug_discontinuities(boot TEXT,seq INTEGER,ieee TEXT,received REAL,reason TEXT,PRIMARY KEY(boot,seq));''')
        with self.db:
            for row in self.db.execute('SELECT data FROM plug_jobs').fetchall():
                j=json.loads(row[0])
                if j['state'] in ACTIVE and j['action'] not in ('read','commission'):
                    j.update(state='uncertain' if j['state']=='sending' else 'cancelled',request_id=None,message='Dashboard restarted; load/settings command was not replayed. Read actual state before another action.')
                    self._save_plug(j)
    def _save_plug(self,j):self.db.execute('INSERT OR REPLACE INTO plug_jobs VALUES(?,?,?)',(j['id'],j['ieee'],json.dumps(j)))
    def plug_document(self):
        with self.lock:return {'jobs':[json.loads(r[0]) for r in self.db.execute("SELECT data FROM plug_jobs ORDER BY (json_extract(data,'$.state') IN ('queued','waiting','sending')) DESC,json_extract(data,'$.created_at') DESC LIMIT 100")]}
    def _plug_busy(self,ieee):
        return self.db.execute("SELECT 1 FROM plug_jobs WHERE ieee=? AND json_extract(data,'$.state') IN ('queued','waiting','sending') LIMIT 1",(ieee,)).fetchone() is not None
    def start_plug(self,body,now=None):
        if not isinstance(body,dict) or set(body)!={'ieee','endpoint','action','settings'} or not isinstance(body['ieee'],str) or not re.fullmatch('[0-9a-f]{16}',body['ieee']) or type(body['endpoint']) is not int or not 1<=body['endpoint']<=240 or not isinstance(body['action'],str) or not isinstance(body['settings'],dict):raise DashboardError('Provide ieee, endpoint, action and settings.')
        operations=plugs.steps(body['action'],body['settings']);now=time.time() if now is None else now
        with self.lock,self.db:
            d=self._get(body['ieee']);ep=body['endpoint'];desc=d.get('endpoints',{}).get(str(ep),{})
            if not d.get('active') or not plugs.identified(d,ep) or not {6,1794,64529}<=set(desc.get('input_clusters',[])):raise DashboardError('Requires observed SONOFF/eWeLink S60ZBTPG identity and discovered relay, metering and vendor clusters on this endpoint.')
            if self._plug_busy(d['ieee']):raise DashboardError('Wait for or cancel the active plug job.',409)
            for table in ('commissioning','display_jobs'):
                row=self.db.execute('SELECT data FROM '+table+' WHERE ieee=?',(d['ieee'],)).fetchone()
                if row and json.loads(row[0])['state'] in ACTIVE:raise DashboardError('Another device setup is active.',409)
            # Prune terminal jobs; active operations and the most recent 100 records are retained.
            self.db.execute("DELETE FROM plug_jobs WHERE json_extract(data,'$.state') NOT IN ('queued','waiting','sending') AND id NOT IN (SELECT id FROM plug_jobs ORDER BY json_extract(data,'$.created_at') DESC LIMIT 99)")
            j=dict(id=str(uuid.uuid4()),ieee=d['ieee'],endpoint=ep,action=body['action'],settings=body['settings'],steps=operations,state='queued',step=0,attempt=0,request_id=None,deadline=None,created_at=now,expires_at=now+(1800 if body['action']=='commission' else 300),next_attempt=now,results=[],message='Queued; actual device responses/readback are required.',primed=False,boot_id=None)
            self._save_plug(j);return j
    def cancel_plug(self,job_id):
        if not isinstance(job_id,str) or not re.fullmatch('[0-9a-f-]{36}',job_id):raise DashboardError('Invalid plug job identity.')
        with self.lock,self.db:
            row=self.db.execute('SELECT data FROM plug_jobs WHERE id=?',(job_id,)).fetchone()
            if not row:raise DashboardError('Plug job not found.',404)
            j=json.loads(row[0]);j.update(state='cancelled',request_id=None,message='Cancelled. An in-flight command may already have applied.');self._save_plug(j);return j
    def plug_event(self,boot,e,received):
        if e.get('type')!='commissioning':return
        for row in self.db.execute('SELECT data FROM plug_jobs WHERE ieee=?',(e.get('ieee'),)).fetchall():
            j=json.loads(row[0])
            if j['state']!='sending' or j['request_id']!=e.get('request_id') or j['boot_id']!=boot:continue
            s=j['steps'][j['step']]
            if (e.get('operation'),e.get('endpoint'),e.get('cluster'),e.get('attribute'))!=(s['op'],j['endpoint'],s['cluster'],s['attribute']):continue
            j['results'].append(dict(e,received_at=received));j['results']=j['results'][-96:]
            ok=e.get('phase')=='response' and e.get('status')==0
            if s['op']=='plug_read':
                dtype=plugs.READS[(s['cluster'],s['attribute'])];ok=ok and e.get('data_type')==dtype
                if 'expected' in s:ok=ok and e.get('raw')==s['expected']
                if 'expected_hex' in s:ok=ok and e.get('raw_hex')==s['expected_hex']
            if s['op']=='plug_read_reporting':
                dtype,lo,hi,change=plugs.REPORTS[(s['cluster'],s['attribute'])]
                ok=ok and all(e.get(k)==v for k,v in [('data_type',dtype),('min_interval',lo),('max_interval',hi),('reportable_change',change)])
            j['request_id']=None
            if ok:
                j['step']+=1;j.update(attempt=0,next_attempt=received,state=('acknowledged_unverified' if j['action']=='inching' else 'verified') if j['step']==len(j['steps']) else 'queued',message='Device acknowledged inching; device-side timing/readback is unverified.' if j['action']=='inching' else 'Device response/readback verified.' if j['step']==len(j['steps']) else 'Device setup in progress.')
            else:j.update(state='uncertain' if s['op'] in ('plug_relay','plug_write','plug_inching') and e.get('phase')!='response' else 'failed',message='Device rejected or did not confirm the operation. Read actual values; no load command is replayed.')
            self._save_plug(j)
    def _plug_counter(self,boot,e,received,d):
        if e.get('cluster')!=1794 or e.get('attribute')!=0 or e.get('data_type')!=0x25 or type(e.get('raw')) is not int or not 0<=e['raw']<0xffffffffffff or not plugs.identified(d,e['endpoint']):return
        previous=d.get('attributes',{}).get(f"{e['endpoint']}:1794:0")
        if previous and type(previous.get('raw')) is int and 0<=previous['raw']<0xffffffffffff and (e['raw']<previous.get('raw',0) or previous.get('source_boot')!=boot):
            reason='counter_decrease_reset_or_rollover' if e['raw']<previous.get('raw',0) else 'gateway_epoch_changed'
            self.db.execute('INSERT OR IGNORE INTO plug_discontinuities VALUES(?,?,?,?,?)',(boot,e['seq'],e['ieee'],received,reason))
            self.db.execute('DELETE FROM plug_discontinuities WHERE received<?',(received-30*86400,))
    def plug_details(self,d):
        if not plugs.identified(d):return None
        ep=next((int(k) for k in d['endpoints'] if plugs.identified(d,int(k))),None)
        controllable=bool(d.get('active') and ep is not None and {6,1794,64529}<=set(d['endpoints'][str(ep)].get('input_clusters',[])))
        attrs=d['attributes'];settings={}
        for name,c,a in [('startup_behavior',6,0x4003),('network_indicator',64529,1),('outlet_protection',64529,0x7007),('protection',64529,0x7003)]:
            v=attrs.get(f'{ep}:{c}:{a}');settings[name]=None if not v else {'raw':v.get('raw'),'raw_hex':v.get('raw_hex'),'received_at':v.get('received')}
        relay=attrs.get(f'{ep}:6:0',{});derived=None
        if relay.get('value') is False and time.time()-relay.get('received',0)<=self.configuration_document()['devices'][d['ieee']]['freshness_seconds']:
            derived={'power_w':0,'current_a':0,'basis':'derived_from_confirmed_off','received_at':relay['received']}
        gaps=[dict(received_at=r[0],reason=r[1]) for r in self.db.execute('SELECT received,reason FROM plug_discontinuities WHERE ieee=? ORDER BY received DESC LIMIT 50',(d['ieee'],))]
        latest=next((j for j in self.plug_document()['jobs'] if j['ieee']==d['ieee']),None)
        if latest:latest={k:latest[k] for k in ('id','action','state','message','settings','step','created_at')}
        return {'controllable':controllable,'latest_job':latest,'model':plugs.MODEL,'hardware_status':'not_tested','endpoint':ep,'settings':settings,'effective_off':derived,'energy_discontinuities':gaps,'energy_policy':'Raw cumulative/device period totals; no inferred consumption deltas. Period boundaries/timezone are device-defined and unverified.','routing':{'model_role':'router_capable','observed_mac_capability':d.get('capability'),'full_function_device':bool(d['capability']&2) if type(d.get('capability')) is int else None,'path_verification':'unverified'},'capabilities':plugs.profiles()['capabilities']}

def drive_plugs(store,gateway,health,now=None):
    now=time.time() if now is None else now;send=None;prime=None
    with store.lock,store.db:
        for j in store.plug_document()['jobs']:
            if j['state'] not in ACTIVE:continue
            if now>=j['expires_at']:j.update(state='expired',request_id=None,message='Job expired; partial settings may have applied.')
            elif not health.get('plug_extensions'):j.update(state='failed',message='Gateway smart-plug firmware required.')
            elif not health.get('ready'):continue
            elif j['state']=='sending' and (now>=j['deadline'] or j['boot_id']!=health['boot_id']):
                op=j['steps'][j['step']]['op']
                j.update(state='uncertain' if op in ('plug_relay','plug_write','plug_inching') else 'failed' if j['attempt']>=3 else 'waiting',request_id=None,next_attempt=now+5,message='No confirmed result; load/settings writes are never automatically replayed.')
            if send is None and prime is None and j['state'] in ('queued','waiting') and now>=j['next_attempt']:
                if j.get('primed_boot')!=health['boot_id']:
                    prime=(j['ieee'],j['endpoint']);j.update(primed_boot=health['boot_id'],next_attempt=now+3)
                else:
                    d=store._get(j['ieee'])
                    if not d.get('active') or not plugs.identified(d,j['endpoint']):j.update(state='failed',message='Device identity/membership changed.')
                    else:
                        s=j['steps'][j['step']];rid=str(uuid.uuid4());send={k:v for k,v in s.items() if not k.startswith('expected')};send.update(ieee=j['ieee'],endpoint=j['endpoint'],request_id=rid)
                        j.update(state='sending',attempt=j['attempt']+1,request_id=rid,boot_id=health['boot_id'],deadline=now+27,message='Requested; waiting for device acknowledgement/readback.')
            store._save_plug(j)
    if prime:
        for attr in (4,5):
            try:gateway.request('/api/v1/commands',{'op':'read','ieee':prime[0],'endpoint':prime[1],'cluster':0,'attribute':attr})
            except Exception:pass
    if send:
        try:gateway.request('/api/v1/commands',send)
        except Exception:pass  # Unknown submission outcome; preserve correlation, never replay a write.
