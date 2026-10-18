"""S60ZBTPG protocol and capabilities. No physical compatibility claim."""
import math
import struct
from decimal import Decimal
from .dashboard import DashboardError

MODEL = 'SONOFF S60ZBTPG'
REFERENCE_REVISION = '72398c3063aca492fe936bf01e0a5fffad28fbd1'
METRICS = {(64529,0x7004):('Current','A'),(64529,0x7005):('Voltage','V'),
    (64529,0x7006):('Active power','W'),(64529,0x7009):('Energy today','kWh'),
    (64529,0x700a):('Energy this month','kWh'),(64529,0x700b):('Energy yesterday','kWh'),
    (1794,0):('Accumulated energy','kWh')}
READS = {(6,0):0x10,(6,0x4003):0x30,(64529,1):0x10,(64529,0x7007):0x20,
    (64529,0x7003):0x42,(1794,0):0x25,(1794,0x300):0x30,(1794,0x301):0x22,(1794,0x302):0x22,
    **{k:0x23 for k in METRICS if k[0]==64529}}
WRITES = {(6,0x4003):(0x30,0,255),(64529,1):(0x10,0,1),(64529,0x7007):(0x20,0,1)}
REPORTS = {(6,0):(0x10,1,1800,0), (1794,0):(0x25,60,3600,1),
    **{k:(0x23,10 if k[1]<=0x7006 else 60,3600,2 if k[1]==0x7004 else 50 if k[1]>=0x7009 else 0) for k in METRICS if k[0]==64529}}

def identified(device,endpoint=None):
    attrs=device.get('attributes',{}).values()
    model=any(a.get('cluster')==0 and a.get('attribute')==5 and a.get('raw')=='S60ZBTPG' and (endpoint is None or a.get('endpoint')==endpoint) for a in attrs)
    manufacturer=any(a.get('cluster')==0 and a.get('attribute')==4 and a.get('raw') in ('SONOFF','eWeLink') and (endpoint is None or a.get('endpoint')==endpoint) for a in attrs)
    return model and manufacturer

def profiles():
    return {'reference_revision':REFERENCE_REVISION,'reference_url':'https://github.com/Koenkk/zigbee-herdsman-converters/blob/'+REFERENCE_REVISION+'/src/devices/sonoff.ts',
        'model':MODEL,'hardware_status':'not_tested','recommended_freshness_seconds':4500,'ratings':{'current_a':13,'power_w':3250},
        'capabilities':{k:{'status':v,'hardware':'not_tested'} for k,v in {
            'relay':'prepared_readback','metering':'prepared_raw_preserved','reporting':'prepared_readback',
            'startup_behavior':'prepared_readback','network_indicator':'prepared_readback','outlet_protection':'prepared_readback',
            'overload_thresholds':'prepared_readback','inching':'prepared_acknowledgement_only',
            'period_energy':'prepared_device_totals_boundaries_unverified','routing':'capability_observation_only',
            'schedules':'deferred_issue_31','countdown':'deferred_issue_31','scenes':'deferred_issue_31','ota':'deferred_issue_30'}.items()}}

def scaled(value,low,high,scale=1000,step='.1'):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high or Decimal(str(value))%Decimal(step):
        raise DashboardError(f'Use {low}..{high} in steps of {step}.')
    return int(Decimal(str(value))*scale)

def inching(settings):
    if not isinstance(settings,dict) or set(settings)!={'enabled','mode','seconds'} or type(settings['enabled']) is not bool or settings['mode'] not in ('on','off'):
        raise DashboardError('Inching requires enabled, mode (on/off), and seconds.')
    ticks=scaled(settings['seconds'],.5,3599.5,2,'.5')
    data=bytes([1,0x17,7,0x80,(0x80 if settings['enabled'] else 0)|(settings['mode']=='on'),0,ticks&255,ticks>>8,0,0])
    checksum=0
    for b in data:checksum^=b
    return (data+bytes([checksum])).hex()

def protection(settings):
    mandatory={'max_current','max_power'};optional={'enable_min_current','min_current','enable_max_voltage','max_voltage','enable_min_voltage','min_voltage','enable_min_power','min_power'}
    if not isinstance(settings,dict) or not mandatory<=settings.keys() or settings.keys()-mandatory-optional:raise DashboardError('Protection requires max_current/max_power and supported complete optional limits.')
    raw={k:scaled(settings[k],.1,13 if k.endswith('current') else 3250) for k in mandatory}
    flags=[1,0,1]
    for flag,field in [('enable_min_current','min_current'),('enable_max_voltage','max_voltage'),('enable_min_voltage','min_voltage'),('enable_min_power','min_power')]:
        if flag in settings and type(settings[flag]) is not bool:raise DashboardError('Protection enable flags must be boolean.')
        enabled=settings.get(flag,False)
        if (field in settings)!=enabled:raise DashboardError('Each enabled protection limit needs a value; disabled limits must omit the value.')
        if enabled:
            raw[field]=scaled(settings[field],165 if 'voltage' in field else .1,277 if 'voltage' in field else 13 if 'current' in field else 3250,step='1' if 'voltage' in field else '.1')
            flags[0 if 'current' in field else 1 if 'voltage' in field else 2]|=1 if field.startswith('max') else 2
    for metric in ('current','power','voltage'):
        if 'min_'+metric in raw and 'max_'+metric in raw and raw['min_'+metric]>=raw['max_'+metric]:raise DashboardError('Minimum protection limit must be below maximum.')
    data=bytes([4,0,*flags])+b''.join(struct.pack('<I',raw[k]) for k in ('max_current','min_current','max_voltage','min_voltage','max_power','min_power') if k in raw)
    return bytes([4,len(data)-2,*flags]).hex()+data[5:].hex()

def decode_protection(hex_value):
    try:
        data=bytes.fromhex(hex_value)
        if len(data)<5 or data[0]!=4 or data[1]!=len(data)-2 or data[2] not in (1,3) or data[3]>3 or data[4] not in (1,3):return None
        values={};offset=5
        for i,metric in enumerate(('current','voltage','power')):
            for bit,side in ((1,'max'),(2,'min')):
                if data[2+i]&bit:
                    values[side+'_'+metric]=struct.unpack_from('<I',data,offset)[0]/1000;offset+=4
        return values if offset==len(data) else None
    except (ValueError,struct.error,TypeError):return None

def normalize(device,endpoint,cluster,attribute,dtype,raw):
    if not identified(device,endpoint) or type(raw) is not int:return None,None
    if (cluster,attribute) in METRICS and cluster==64529 and dtype==0x23 and 0<=raw<0xffffffff:return raw/1000,METRICS[(cluster,attribute)][1]
    if cluster==1794 and attribute==0 and dtype==0x25 and 0<=raw<0xffffffffffff:
        attrs=device.get('attributes',{});mul=attrs.get(f'{endpoint}:1794:769',{});div=attrs.get(f'{endpoint}:1794:770',{})
        m,d=mul.get('raw'),div.get('raw')
        unit=attrs.get(f'{endpoint}:1794:768',{})
        if unit.get('data_type')==0x30 and unit.get('raw')==0 and mul.get('data_type')==div.get('data_type')==0x22 and type(m) is int and type(d) is int and 0<m<0xffffff and 0<d<0xffffff:return raw*m/d,'kWh'
    return None,None

def steps(action,settings):
    if action=='relay':
        if set(settings)!={'state'} or type(settings['state']) is not bool:raise DashboardError('Relay state must be boolean.')
        return [{'op':'plug_relay','cluster':6,'attribute':0,'value':int(settings['state'])},{'op':'plug_read','cluster':6,'attribute':0,'expected':int(settings['state'])}]
    if action in ('startup_behavior','network_indicator','outlet_protection'):
        if set(settings)!={'value'}:raise DashboardError('Provide one setting value.')
        if action=='startup_behavior':
            choices={'off':0,'on':1,'toggle':2,'previous':255}
            if not isinstance(settings['value'],str) or settings['value'] not in choices:raise DashboardError('Unsupported startup behavior.')
            value=choices[settings['value']];cluster,attr=6,0x4003
        else:
            if type(settings['value']) is not bool:raise DashboardError('Value must be boolean.')
            value=int(settings['value']);cluster,attr=64529,1 if action=='network_indicator' else 0x7007
        return [{'op':'plug_write','cluster':cluster,'attribute':attr,'value':value},{'op':'plug_read','cluster':cluster,'attribute':attr,'expected':value}]
    if action=='inching':return [{'op':'plug_inching','cluster':64529,'attribute':0,'payload':inching(settings)}]
    if action=='protection':
        payload=protection(settings)
        return [{'op':'plug_write','cluster':64529,'attribute':0x7003,'payload':payload},{'op':'plug_read','cluster':64529,'attribute':0x7003,'expected_hex':payload}]
    if settings:raise DashboardError('Read/setup actions do not take settings.')
    reads=[{'op':'plug_read','cluster':c,'attribute':a} for c,a in READS]
    # Scaling must precede energy so its first sample can be normalized.
    reads.sort(key=lambda x:0 if x['cluster']==1794 and x['attribute'] in (768,769,770) else 1)
    if action=='read':return reads
    if action=='commission':
        return [{'op':'plug_bind','cluster':c,'attribute':0} for c in (6,64529,1794)]+[s for (c,a) in REPORTS for s in [{'op':'plug_configure','cluster':c,'attribute':a},{'op':'plug_read_reporting','cluster':c,'attribute':a}]]+reads
    raise DashboardError('Unknown smart plug action.')


def validate_command(c):
    import re
    common={'op','ieee','endpoint','request_id','cluster','attribute'}
    if not isinstance(c,dict) or not isinstance(c.get('ieee'),str) or not re.fullmatch('[0-9a-f]{16}',c['ieee']) or type(c.get('endpoint')) is not int or not 1<=c['endpoint']<=240 or not isinstance(c.get('request_id'),str) or not re.fullmatch('[0-9a-f-]{36}',c['request_id']):raise ValueError('Invalid plug identity/correlation')
    if type(c.get('cluster')) is not int or type(c.get('attribute')) is not int:raise ValueError('Invalid source')
    key=(c['cluster'],c['attribute']);op=c.get('op');extra=set()
    if op in ('plug_bind','plug_configure','plug_read_reporting','plug_read'):
        allowed=key in READS if op=='plug_read' else key in REPORTS if op!='plug_bind' else key[0] in (6,1794,64529) and key[1]==0
        if not allowed:raise ValueError('Unsupported plug source')
    elif op=='plug_relay':
        if key!=(6,0) or type(c.get('value')) is not int or c['value'] not in (0,1):raise ValueError('Invalid relay')
        extra={'value'}
    elif op in ('plug_write','plug_inching'):
        if 'payload' in c:
            extra={'payload'}
            if not isinstance(c['payload'],str) or not re.fullmatch('[0-9a-f]{2,58}',c['payload']) or len(c['payload'])%2:raise ValueError('Invalid payload')
            if op=='plug_write':
                decoded=decode_protection(c['payload'])
                if key!=(64529,0x7003) or decoded is None:raise ValueError('Invalid protection')
                settings={k:v for k,v in decoded.items() if k in ('max_current','max_power')}
                for k,v in decoded.items():
                    if k not in settings:settings['enable_'+k]=True;settings[k]=v
                if protection(settings)!=c['payload']:raise ValueError('Invalid protection limits')
            else:
                b=bytes.fromhex(c['payload']);x=0
                for v in b:x^=v
                if key!=(64529,0) or len(b)!=11 or b[:4]!=bytes([1,23,7,128]) or b[4]&~129 or b[5] or b[8] or b[9] or not 1<=int.from_bytes(b[6:8],'little')<=7199 or x:raise ValueError('Invalid inching')
        else:
            extra={'value'};v=c.get('value')
            if op!='plug_write' or key not in WRITES or type(v) is not int or v not in ((0,1,2,255) if key==(6,0x4003) else (0,1)):raise ValueError('Invalid scalar setting')
    else:raise ValueError('Unsupported plug operation')
    if set(c)!=common|extra:raise ValueError('Unexpected fields')
    return c
