"""Local sensor profiles and bounded SONOFF 02UL codecs. Hardware verification pending."""
import math
import struct
from decimal import Decimal, InvalidOperation
from .dashboard import DashboardError

REFERENCE_REVISION = '3956a2c75e37e467ca5cb9e537923317fdbe80de'
REFERENCE_URL = 'https://github.com/Koenkk/zigbee-herdsman-converters/blob/'+REFERENCE_REVISION+'/src/devices/sonoff.ts'
UL = 'SONOFF SNZB-02UL'
MODELS = ('', 'SONOFF SNZB-02WD', 'SONOFF SNZB-02LD', UL)
DISPLAY_FIELDS = {
    'temperature_units': (7,0x21,0,1,1),
    'comfort_temperature_min': (4,0x29,0,50,100),
    'comfort_temperature_max': (3,0x29,0,50,100),
    'comfort_humidity_min': (5,0x21,5,95,100),
    'comfort_humidity_max': (6,0x21,5,95,100),
    'temperature_calibration': (0x2003,0x29,-50,50,100),
    'humidity_calibration': (0x2004,0x29,-50,50,100),
}

def profile_document():
    return {'reference_revision':REFERENCE_REVISION,'reference_url':REFERENCE_URL,
        'profiles':[{'model':model,'hardware_status':'not_tested' if model==UL else 'reports_observed',
            'defaults':{'min_interval':5,'max_interval':1800 if model==UL else 3600,
                'temperature_change':.2,**({} if model.endswith('02LD') else {'humidity_change':1})},
            'recommended_freshness_seconds':2250 if model==UL else 4500,
            'capabilities':{'temperature':'prepared' if model==UL else 'available',
                'humidity':'absent' if model.endswith('02LD') else 'prepared' if model==UL else 'available',
                'battery':'prepared_when_observed','display_settings':'prepared' if model==UL else 'unavailable',
                'clock':'prepared_time_server' if model==UL else 'unavailable',
                'remote_display':'codec_only_transport_deferred' if model==UL else 'unavailable',
                'weather':'codec_only_transport_and_provider_deferred' if model==UL else 'unavailable',
                'ota':'deferred'}} for model in MODELS if model]}

def device_model(device, hint=''):
    observed=next((a.get('raw') for a in device.get('attributes',{}).values() if a.get('cluster')==0 and a.get('attribute')==5 and isinstance(a.get('raw'),str)),None)
    return ('SONOFF '+observed) if observed in ('SNZB-02WD','SNZB-02LD','SNZB-02UL') else hint

def sensor_endpoint(device, endpoint):
    desc=device.get('endpoints',{}).get(str(endpoint),{})
    return bool({1026,1029}.intersection(desc.get('input_clusters',[]))) and (desc.get('device_id')==0x0302 or device_model(device) in MODELS[1:])

def scaled(value,low,high,scale=100,step=.1):
    if type(value) not in (int,float) or not math.isfinite(value) or not low<=value<=high:
        raise DashboardError(f'Value must be {low}..{high}.',422)
    try:
        raw=Decimal(str(value))*scale
        if raw!=raw.to_integral_value() or Decimal(str(value))%Decimal(str(step)):
            raise InvalidOperation
    except InvalidOperation:raise DashboardError(f'Use increments of {step}.',422)
    return int(raw)

def display_settings(settings):
    if not isinstance(settings,dict) or not settings or len(settings)>7 or set(settings)-DISPLAY_FIELDS.keys():
        raise DashboardError('Choose supported display settings.',422)
    commands=[]
    for key,value in settings.items():
        attribute,dtype,low,high,scale=DISPLAY_FIELDS[key]
        if key=='temperature_units':
            if value not in ('celsius','fahrenheit'):raise DashboardError('Unknown temperature units.',422)
            raw=0 if value=='celsius' else 1
        else:raw=scaled(value,low,high,scale)
        commands.extend([{'op':'write_display','cluster':0xfc11,'attribute':attribute,'value':raw},
            {'op':'read_display','cluster':0xfc11,'attribute':attribute,'expected_value':raw,'expected_type':dtype}])
    for kind in ('temperature','humidity'):
        lo,hi=(settings.get(f'comfort_{kind}_{side}') for side in ('min','max'))
        if lo is not None and hi is not None and lo>hi:raise DashboardError('Comfort minimum must not exceed maximum.',422)
    return commands

# These payload-only helpers are deliberately not a gateway write interface.
# Source offsets are recorded in docs/SNZB_02UL.md; no external provider is called.
def remote_display_payload(kind,value=None,enabled=True):
    if kind not in ('temperature','humidity','pressure','all'):raise DashboardError('Unknown remote display type.',422)
    if type(enabled) is not bool:raise DashboardError('enabled must be boolean.',422)
    if kind=='all':
        if enabled or value is not None:raise DashboardError('all is supported only for disabling remote display.',422)
        items=b''.join(bytes([i,0,0,0]) for i in range(3));count=3
    else:
        i=('temperature','humidity','pressure').index(kind)
        if not enabled:
            if value is not None:raise DashboardError('Disabled sources have no value.',422)
            item=b''
        elif kind=='temperature':item=struct.pack('<h',scaled(value,-20,60))
        elif kind=='humidity':item=struct.pack('<H',scaled(value,5,95,step=1))
        else:item=struct.pack('<i',scaled(value,700,1100))
        items=bytes([i,0,int(enabled),len(item)])+item;count=1
    return bytes([1,1,0,3,1+len(items),count])+items

def weather_reply_payload(request,weather):
    mapping={'sunny':0,'partly_cloudy':1,'overcast':2,'rain':3,'snow':4,'windy':5}
    if not isinstance(request,bytes) or len(request)!=9 or request[0]!=0:
        raise DashboardError('Unsupported weather request payload.',422)
    if weather not in mapping:raise DashboardError('Select a known weather state; no invented fallback.',422)
    return bytes([0,1,mapping[weather]])

ZIGBEE_EPOCH = 946684800

def zigbee_time(unix_time):
    if type(unix_time) is not int or not ZIGBEE_EPOCH<=unix_time<ZIGBEE_EPOCH+0xffffffff:
        raise DashboardError('Time is outside the Zigbee UTC range.',422)
    return unix_time-ZIGBEE_EPOCH
