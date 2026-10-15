"""Durable, bounded temperature/humidity commissioning. No network I/O under DB lock."""
import copy
import json
import math
import re
import time
import uuid
from decimal import Decimal, InvalidOperation
from .dashboard import DashboardError

ACTIVE = {'queued', 'waiting', 'sending'}

def policy_input(body):
    fields = {'ieee','endpoint','min_interval','max_interval','temperature_change','humidity_change','model_hint'}
    if not isinstance(body, dict) or set(body) != fields:
        raise DashboardError('Provide exactly the documented reporting policy fields.', 422)
    if not isinstance(body['ieee'], str) or not re.fullmatch('[0-9a-f]{16}', body['ieee']):
        raise DashboardError('Invalid IEEE address.', 422)
    for key, low, high in [('endpoint',1,240),('min_interval',0,65534),('max_interval',1,65534)]:
        if type(body[key]) is not int or not low <= body[key] <= high:
            raise DashboardError('Invalid '+key+'. Special disabling intervals are unsupported.', 422)
    if body['min_interval'] > body['max_interval']:
        raise DashboardError('Minimum interval must not exceed maximum.', 422)
    result = dict(body)
    for key, maximum in [('temperature_change',32767),('humidity_change',10000)]:
        value = body[key]
        if type(value) not in (int,float) or not math.isfinite(value):
            raise DashboardError('Invalid '+key,422)
        try:
            raw = Decimal(str(value))*100
            if raw != raw.to_integral_value() or not 1 <= raw <= maximum:
                raise InvalidOperation
        except InvalidOperation:
            raise DashboardError(key+' must be positive, in hundredths, within the supported range.',422)
        result[key+'_raw'] = int(raw)
    if body['model_hint'] not in ('', 'SONOFF SNZB-02WD'):
        raise DashboardError('Unsupported model hint; this is user-supplied identity.',422)
    return result


def steps(policy, poll_control):
    result=[]
    # Bind check-ins first so future wake windows can help resume a partial setup.
    if poll_control: result.append({'op':'bind','cluster':32})
    for cluster, key in [(1026,'temperature_change_raw'),(1029,'humidity_change_raw')]:
        result.extend([{'op':'bind','cluster':cluster}, {'op':'configure_reporting','cluster':cluster,'attribute':0,
            'min_interval':policy['min_interval'],'max_interval':policy['max_interval'],'reportable_change':policy[key]},
            {'op':'read_reporting','cluster':cluster,'attribute':0}])
    return result

class CommissioningStore:
    def _init_commissioning(self):
        self.db.execute('CREATE TABLE IF NOT EXISTS commissioning(ieee TEXT PRIMARY KEY REFERENCES devices(ieee), data TEXT NOT NULL)')
        self.db.commit()
    def _save_job(self, job):
        self.db.execute('INSERT OR REPLACE INTO commissioning VALUES(?,?)',(job['ieee'],json.dumps(job)))
    def commissioning_document(self):
        with self.lock:
            jobs=[json.loads(r[0]) for r in self.db.execute('SELECT data FROM commissioning ORDER BY ieee')]
            for job in jobs:
                d=self._get(job['ieee'])
                job['last_contact']=d.get('last_contact') or max((a.get('received',0) for a in d.get('attributes',{}).values()),default=0) or None
                job['identity']={key:d.get('attributes',{}).get(f"{job['policy']['endpoint']}:0:{aid}",{}).get('raw') for key,aid in [('manufacturer',4),('model',5)]}
                job['measurements']=[{'cluster':c,'received_at':a.get('received'), 'origin':a.get('origin','unknown')}
                    for c in (1026,1029) if (a:=d.get('attributes',{}).get(f"{job['policy']['endpoint']}:{c}:0"))]
            return {'jobs':jobs}
    def start_commissioning(self, body, now=None):
        policy=policy_input(body);now=time.time() if now is None else now
        with self.lock,self.db:
            if not self.db.execute('SELECT 1 FROM devices WHERE ieee=?',(policy['ieee'],)).fetchone():
                raise DashboardError('Device not found.',404)
            d=self._get(policy['ieee']);desc=d['endpoints'].get(str(policy['endpoint']),{})
            if not d.get('active') or not {1026,1029}.issubset(desc.get('input_clusters',[])):
                raise DashboardError('Discover an active temperature/humidity endpoint first.',422)
            old=self.db.execute('SELECT data FROM commissioning WHERE ieee=?',(policy['ieee'],)).fetchone()
            if old and json.loads(old[0])['state'] in ACTIVE:
                raise DashboardError('Commissioning already in progress. Cancel before changing policy.',409)
            job={'id':str(uuid.uuid4()),'ieee':policy['ieee'],'policy':policy,'steps':steps(policy,32 in desc.get('input_clusters',[])),
                'state':'queued','step':0,'attempt':0,'created_at':now,'expires_at':now+300,'next_attempt':now,
                'request_id':None,'deadline':None,'results':[],'gateway_boot':None,
                'message':'Wake the sensor with a brief button press; setup expires after five minutes.'}
            self._save_job(job)
            return job
    def cancel_commissioning(self, ieee):
        with self.lock,self.db:
            row=self.db.execute('SELECT data FROM commissioning WHERE ieee=?',(ieee,)).fetchone()
            if not row: raise DashboardError('Commissioning not found.',404)
            job=json.loads(row[0]);job.update(state='cancelled',request_id=None,message='Cancelled. In-flight radio operations may still complete; retry is idempotent.')
            self._save_job(job);return job
    def commissioning_event(self,e,received):
        # Called inside the atomic telemetry/cursor transaction; duplicate events never reach here.
        row=self.db.execute('SELECT data FROM commissioning WHERE ieee=?',(e.get('ieee'),)).fetchone()
        if not row:return
        job=json.loads(row[0])
        if job['state'] not in ACTIVE:return
        if e.get('type') in ('check_in','announce','attribute','endpoint') and job['state']=='waiting':
            job['next_attempt']=min(job['next_attempt'],received)
        if e.get('type')=='commissioning' and e.get('request_id')==job['request_id']:
            expected=job['steps'][job['step']]
            if e.get('operation')!=expected['op'] or e.get('cluster')!=expected['cluster'] or e.get('endpoint')!=job['policy']['endpoint']:return
            record=dict(e,received_at=received);job['results'].append(record);job['results']=job['results'][-32:]
            success=e.get('phase')=='response' and e.get('status')==0
            unsupported=expected['op']=='read_reporting' and e.get('phase')=='response' and e.get('status') in (0x82,0x86,0x8c)
            if success and expected['op']=='read_reporting':
                policy=job['policy'];key='temperature_change_raw' if expected['cluster']==1026 else 'humidity_change_raw'
                success=all(e.get(k)==v for k,v in {'data_type':0x29 if expected['cluster']==1026 else 0x21,'min_interval':policy['min_interval'],'max_interval':policy['max_interval'],'reportable_change':policy[key]}.items())
                if not success:job['message']='Reporting readback differs from requested settings.'
            job['request_id']=None
            if success or unsupported:
                if unsupported:record['verification']='unsupported';job['readback_unsupported']=True
                job['step']+=1;job['attempt']=0;job['next_attempt']=received
                job['state']='queued' if job['step']<len(job['steps']) else 'configured_unverified' if job.get('readback_unsupported') else 'verified'
                job['message']='Reporting setup in progress.' if job['state']=='queued' else 'Device acknowledged setup; observe unsolicited reports to prove delivery.'
            else:
                job['state']='waiting' if job['attempt']<3 else 'failed';job['next_attempt']=received+30
                if 'differs' not in job['message']:job['message']='Device rejected setup or did not respond. Wake it and retry; check range/battery if this persists.'
        self._save_job(job)


def drive_commissioning(store,gateway,health,now=None):
    """One send per poll, at most three attempts per step and five minutes per job.

    Save correlation BEFORE sending, avoiding a fast-response race. A lost HTTP
    response is an uncertain attempt; wait for the radio event before retrying.
    """
    now=time.time() if now is None else now
    command=None; selected=None
    with store.lock,store.db:
        jobs=[json.loads(r[0]) for r in store.db.execute('SELECT data FROM commissioning ORDER BY ieee')]
        for job in jobs:
            # A completed policy is rechecked/reapplied once after a gateway reboot.
            if job['gateway_boot'] and job['gateway_boot']!=health['boot_id'] and job['state'] in (ACTIVE | {'verified','configured_unverified'}):
                job.update(state='queued',step=0,attempt=0,request_id=None,expires_at=now+300,next_attempt=now,readback_unsupported=False)
            job['gateway_boot']=health['boot_id']
            if job['state'] not in ACTIVE:
                store._save_job(job);continue
            if now>=job['expires_at']:
                job.update(state='expired',request_id=None,message='Setup expired. Wake the sensor, check its battery/range and retry.')
            elif health.get('ready') is False:
                store._save_job(job);continue
            elif not health.get('reporting_commissioning'):
                job.update(state='failed',message='Gateway firmware does not support reporting commissioning. Update it first.')
            elif job['state']=='sending' and now>=job['deadline']:
                job.update(state='waiting' if job['attempt']<3 else 'failed',request_id=None,next_attempt=now+30,
                    message='No device acknowledgement. Wake the sensor or check battery/range, then retry.')
            if command is None and job['state'] in ('queued','waiting') and now>=job['next_attempt']:
                rid=str(uuid.uuid4());command=dict(job['steps'][job['step']],ieee=job['ieee'],endpoint=job['policy']['endpoint'],request_id=rid)
                job.update(state='sending',attempt=job['attempt']+1,request_id=rid,deadline=now+27,message='Waiting for device acknowledgement; a brief button press may be needed.')
                selected=copy.deepcopy(job)
            store._save_job(job)
    if command:
        # Arm bounded check-in fast polling; no polling interval settings are modified.
        try:gateway.request('/api/v1/commands',{'op':'reporting_window','ieee':selected['ieee'],'endpoint':selected['policy']['endpoint'],'request_id':str(uuid.uuid4()),'seconds':120})
        except Exception:pass
        if selected['step']==0 and selected['attempt']==1:
            for attribute in (4,5):
                try:gateway.request('/api/v1/commands',{'op':'read','ieee':selected['ieee'],'endpoint':selected['policy']['endpoint'],'cluster':0,'attribute':attribute})
                except Exception:pass
        try:
            response=gateway.request('/api/v1/commands',command)
            if not response.get('accepted'):raise ValueError('not accepted')
        except Exception:
            # Keep request_id/deadline: submission may have reached the device.
            pass
