"""Durable scalar display writes with readback, independent of telemetry/history."""
import json
import re
import time
import uuid
from datetime import datetime
from .dashboard import DashboardError
from .sensors import UL,device_model,display_settings,zigbee_time

ACTIVE={'queued','sending','waiting'}
class DisplayStore:
    def _init_display(self):
        self.db.execute('CREATE TABLE IF NOT EXISTS display_jobs(ieee TEXT PRIMARY KEY REFERENCES devices(ieee),data TEXT NOT NULL)');self.db.commit()
    def _save_display(self,j):self.db.execute('INSERT OR REPLACE INTO display_jobs VALUES(?,?)',(j['ieee'],json.dumps(j)))
    def _model_hint(self,ieee):
        row=self.db.execute('SELECT data FROM commissioning WHERE ieee=?',(ieee,)).fetchone()
        return json.loads(row[0])['policy'].get('model_hint','') if row else ''
    def display_document(self):
        with self.lock:
            return {'jobs':[json.loads(r[0]) for r in self.db.execute('SELECT data FROM display_jobs ORDER BY ieee')]}
    def start_display(self,body,now=None):
        if not isinstance(body,dict) or set(body)!={'ieee','endpoint','settings'} or not isinstance(body.get('ieee'),str) or not re.fullmatch('[0-9a-f]{16}',body['ieee']) or type(body['endpoint']) is not int or not 1<=body['endpoint']<=240:
            raise DashboardError('Provide a valid ieee, endpoint and settings.',422)
        operations=display_settings(body['settings']);now=time.time() if now is None else now
        with self.lock,self.db:
            if not self.db.execute('SELECT 1 FROM devices WHERE ieee=?',(body['ieee'],)).fetchone():raise DashboardError('Device not found.',404)
            d=self._get(body['ieee']);desc=d['endpoints'].get(str(body['endpoint']),{})
            if not d.get('active') or device_model(d,self._model_hint(d['ieee']))!=UL or 0xfc11 not in desc.get('input_clusters',[]):
                raise DashboardError('Display settings require an identified SNZB-02UL endpoint advertising the vendor cluster.',422)
            if self._plug_busy(d['ieee']):raise DashboardError('Cancel or finish the active plug operation first.',409)
            for table in ('commissioning','display_jobs'):
                row=self.db.execute('SELECT data FROM '+table+' WHERE ieee=?',(d['ieee'],)).fetchone()
                if row and json.loads(row[0])['state'] in ACTIVE:raise DashboardError('Wait for or cancel the active sensor setup first.',409)
            # Check new comfort bounds against previously read values when available.
            for kind,attr_min,attr_max in [('temperature',4,3),('humidity',5,6)]:
                known={side:d['attributes'].get(f"{body['endpoint']}:64529:{attr}",{}).get('raw') for side,attr in [('min',attr_min),('max',attr_max)]}
                vals={side:body['settings'].get(f'comfort_{kind}_{side}',known[side]/100 if type(known[side]) in (int,float) else None) for side in ('min','max')}
                if None not in vals.values() and vals['min']>vals['max']:raise DashboardError('Comfort bounds conflict with device readback.',422)
            j=dict(id=str(uuid.uuid4()),ieee=d['ieee'],endpoint=body['endpoint'],settings=body['settings'],steps=operations,
                state='queued',step=0,attempt=0,request_id=None,deadline=None,created_at=now,expires_at=now+300,next_attempt=now,
                results=[],message='Display settings queued. Wake the device; values are not confirmed until read back.')
            self._save_display(j);return j
    def cancel_display(self,ieee):
        if not isinstance(ieee,str) or not re.fullmatch('[0-9a-f]{16}',ieee):raise DashboardError('Invalid device identity.',422)
        with self.lock,self.db:
            row=self.db.execute('SELECT data FROM display_jobs WHERE ieee=?',(ieee,)).fetchone()
            if not row:raise DashboardError('Display job not found.',404)
            j=json.loads(row[0]);j.update(state='cancelled',request_id=None,message='Cancelled; in-flight writes may still complete.');self._save_display(j);return j
    def display_event(self,e,received):
        row=self.db.execute('SELECT data FROM display_jobs WHERE ieee=?',(e.get('ieee'),)).fetchone()
        if not row:return
        j=json.loads(row[0])
        if j['state'] not in ACTIVE:return
        if e.get('type') in ('announce','check_in','attribute') and j['state']=='waiting':j['next_attempt']=min(j['next_attempt'],received)
        if e.get('type')=='commissioning' and e.get('request_id')==j['request_id']:
            expected=j['steps'][j['step']]
            if e.get('operation')!=expected['op'] or e.get('endpoint')!=j['endpoint'] or e.get('cluster')!=64529 or e.get('attribute')!=expected['attribute']:return
            j['results'].append(dict(e,received_at=received));j['results']=j['results'][-48:]
            ok=e.get('phase')=='response' and e.get('status')==0
            if expected['op']=='read_display':ok=ok and e.get('raw')==expected['expected_value'] and e.get('data_type')==expected['expected_type']
            j['request_id']=None
            if ok:
                j['step']+=1;j.update(attempt=0,next_attempt=received,state='verified' if j['step']==len(j['steps']) else 'queued',message='Settings readback verified.' if j['step']==len(j['steps']) else 'Display setup in progress.')
            else:j.update(state='failed' if j['attempt']>=3 else 'waiting',next_attempt=received+30,message='Display write/readback failed or timed out. Wake device and retry; partial writes may already have applied.')
        self._save_display(j)

def drive_display(store,gateway,health,now=None):
    now=time.time() if now is None else now;command=None;j=None
    with store.lock,store.db:
        for row in store.db.execute('SELECT data FROM display_jobs ORDER BY ieee').fetchall():
            job=json.loads(row[0])
            if job['state'] not in ACTIVE:continue
            if now>=job['expires_at']:job.update(state='expired',request_id=None,message='Display setup expired; partial writes may have applied.')
            elif not health.get('sensor_extensions'):job.update(state='failed',message='Gateway firmware upgrade required for display settings.')
            elif health.get('ready') is False:continue
            elif job['state']=='sending' and now>=job['deadline']:job.update(state='failed' if job['attempt']>=3 else 'waiting',request_id=None,next_attempt=now+30,message='No display acknowledgement; wake device and retry.')
            if command is None and job['state'] in ('queued','waiting') and now>=job['next_attempt']:
                step=job['steps'][job['step']];rid=str(uuid.uuid4())
                command={k:v for k,v in step.items() if not k.startswith('expected_')}
                command.update(ieee=job['ieee'],endpoint=job['endpoint'],request_id=rid)
                job.update(state='sending',attempt=job['attempt']+1,request_id=rid,deadline=now+27,message='Waiting for display acknowledgement/readback.');j=dict(job)
            store._save_display(job)
    if command:
        try:gateway.request('/api/v1/commands',{'op':'reporting_window','ieee':j['ieee'],'endpoint':j['endpoint'],'request_id':str(uuid.uuid4()),'seconds':120})
        except Exception:pass
        try:gateway.request('/api/v1/commands',command)
        except Exception:pass  # Submission may have reached the sensor; preserve correlation.

def drive_clock(poller,health):
    """Lease current Pi UTC/offset to the local Time server every five minutes.

    No device or external weather service is contacted. Firmware invalidates an
    expired lease; a gateway reboot causes an immediate fresh sync.
    """
    if not health.get('sensor_extensions') or not health.get('ready'):return
    now=time.time();last=getattr(poller,'clock_synced',None)
    if last and last[0]==health['boot_id'] and now-last[1]<300:return
    attempt=getattr(poller,'clock_attempt',None)
    if attempt and attempt[0]==health['boot_id'] and now-attempt[1]<30:return
    with poller.store.lock:
        present=any(device_model(d,poller.store._model_hint(d['ieee']))==UL for d in poller.store.snapshot())
    if not present:return
    stamp=int(now);zigbee_time(stamp);offset=int(datetime.fromtimestamp(now).astimezone().utcoffset().total_seconds())
    poller.clock_attempt=(health['boot_id'],now)
    try:
        result=poller.gateway.request('/api/v1/commands',{'op':'sync_clock','unix_time':stamp,'utc_offset':offset})
        if result.get('accepted'):poller.clock_synced=(health['boot_id'],now)
    except Exception:pass
