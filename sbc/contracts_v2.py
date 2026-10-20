"""Implemented dashboard v2 contracts, separate from the board API."""
from .contracts import obj, array, integer, ref, response
from .dashboard import RANGES
from .grid_layout import BREAKPOINTS


def capabilities_v2():
    return {"api_version": "2", "widget_types": ["numeric", "chart"],
        "features": {"configuration": True, "history_query": True, "dashboard_layouts": True, "reporting_commissioning": True,"user_profiles":True,"sensor_extensions":True,"signal_history":True,"all_overview_layout":True,"smart_plugs":True,"grid_layouts":True,"system_dashboard":True},
        "limits": {"configuration_bytes": 65536, "widgets": 100, "locations": 50,
            "device_overrides": 50, "history_page": 500, "history_days": 31,
            "history_retention_days": 60,"all_columns":6,"all_min_tile_width":200,"all_max_tile_width":640,"profiles":20,"profile_name_chars":80, "chart_ranges": list(RANGES)}}


def contract_v2():
    source = obj({"ieee": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
        "endpoint": integer(1, 240), "cluster": integer(0, 65535), "attribute": integer(0, 65535)},
        ("ieee", "endpoint", "cluster", "attribute"), additionalProperties=False)
    widget = obj({"id": {"type": "string", "pattern": "^[a-z][a-z0-9-]{0,63}$"},
        "type": {"enum": ["numeric", "chart"]}, "title": {"type": "string", "minLength": 1, "maxLength": 80},
        "source": source, "position": integer(0, 99), "time_range": {"enum": list(RANGES)}},
        ("id", "type", "title", "source", "position", "time_range"), additionalProperties=False)
    settings = obj({"name": {"type": "string", "minLength": 1, "maxLength": 80},
        "location_id": {"type": ["string", "null"]}, "freshness_seconds": integer(60, 604800)},
        additionalProperties=False)
    grid_item = obj({"id":{"type":"string","pattern":"^[0-9a-f]{16}$"},
        "x":integer(0,11),"y":integer(0,1000),"w":integer(1,12),"h":integer(3,20)},
        ("id","x","y","w","h"),additionalProperties=False)
    location_grid_item = obj({**grid_item['properties'],'id':{'type':'string','pattern':'^[a-z][a-z0-9-]{0,63}$'}},grid_item['required'],additionalProperties=False)
    location_grid = obj({key:array(obj({**location_grid_item['properties'],'x':integer(0,cols-1),'w':integer(1,cols)},location_grid_item['required'],additionalProperties=False),maxItems=100) for key,cols in BREAKPOINTS.items()},tuple(BREAKPOINTS),additionalProperties=False)
    metric_style = obj({'trend':{'type':'boolean'},'scale': {'type':'number','minimum':75,'maximum':150},
        'size': {'type':'number','minimum':24,'maximum':96},
        'font': {'enum':['system','mono','serif','rounded']},
        'color': {'type':'string','pattern':'^(auto|#[0-9a-fA-F]{6})$'}}, additionalProperties=False)
    presentation = obj({'version': {'const':1}, 'defaults':metric_style,
        'all': {'type':'object','maxProperties':50,'propertyNames':{'pattern':'^[0-9a-f]{16}$'},'additionalProperties':metric_style},
        'widgets': {'type':'object','maxProperties':100,'propertyNames':{'pattern':'^[a-z][a-z0-9-]{0,63}$'},'additionalProperties':metric_style}},
        ('version','defaults','all','widgets'), additionalProperties=False)
    grid_layout = obj({"presentation":presentation,"version":{"const":1},"theme":{"enum":["light","dark"]},"locations":{"type":"object","maxProperties":50,"propertyNames":{"pattern":"^[a-zA-Z0-9-]{1,64}$"},"additionalProperties":location_grid},
        "all":obj({key:array(obj({**grid_item["properties"],"x":integer(0,cols-1),"w":integer(1,cols)},
            grid_item["required"],additionalProperties=False),maxItems=50) for key,cols in BREAKPOINTS.items()},
            tuple(BREAKPOINTS),additionalProperties=False)},("version","theme","all"),additionalProperties=False)
    editable = obj({"locations": array(obj({"id": {"type": "string"}, "name": {"type": "string", "minLength": 1, "maxLength": 80}}, ("id", "name"), additionalProperties=False), maxItems=50),
        "devices": {"type": "object", "maxProperties": 50, "propertyNames": {"pattern": "^[0-9a-f]{16}$"}, "additionalProperties": settings},
        "dashboard": obj({"title": {"type": "string", "minLength": 1, "maxLength": 80},
            "temperature_unit": {"enum": ["celsius", "fahrenheit"]}, "widgets": array(widget, maxItems=100),
            "grid_layout": grid_layout,
            "all_layout": obj({"columns":integer(0,6),"min_tile_width":dict(integer(200,640),multipleOf=20),
                "order":array({"type":"string","pattern":"^[0-9a-f]{16}$"},maxItems=50,uniqueItems=True)},
                ("columns","min_tile_width","order"),additionalProperties=False)},
            ("title", "temperature_unit", "widgets"), additionalProperties=False)},
        ("locations", "devices", "dashboard"), additionalProperties=False)
    measurement = obj({"endpoint": integer(1, 240), "cluster": integer(0, 65535), "attribute": integer(0, 65535),
        "origin":{"enum":["report","read_response","unknown"]}, "freshness_seconds":integer(60,604800),"low_battery":{"type":"boolean"}, "label": {"type": "string"}, "value": {"type": ["number", "boolean", "null"]}, "unit": {"type": "string"},
        "received_at": {"type": ["number", "null"]}, "quality": {"enum": ["valid", "invalid", "missing", "stale"]}},
        ("endpoint", "cluster", "attribute", "label", "value", "unit", "received_at", "quality"))
    signal_metadata = {"boot_id": {"type": "string"}, "seq": integer(),
        "source_endpoint": {"type": ["integer", "null"]},
        "source_cluster": {"type": ["integer", "null"]},
        "source_attribute": {"type": ["integer", "null"]},
        "event_type": {"type": "string"}, "origin": {"type": "string"}}
    signal = obj({**signal_metadata,
        "value": {"type": ["integer", "null"], "minimum": -128, "maximum": 126},
        "unit": {"const": "dBm"}, "received_at": {"type": ["number", "null"]},
        "quality": {"enum": ["valid", "stale", "missing"]},
        "endpoint": {"const": 1}, "cluster": {"const": 65535}, "attribute": {"const": 0},
        "freshness_seconds": integer(60, 604800), "ieee": {"type": "string"},
        "label": {"const": "Signal strength"}},
        ("value", "unit", "received_at", "quality", "endpoint", "cluster", "attribute", "freshness_seconds", "label"))
    definitions = {
        "ConfigurationInput": editable,
        "Configuration": obj({**editable["properties"], "schema_version": {"const": 1}, "revision": integer(1)},
            ("schema_version", "revision", "locations", "devices", "dashboard"), additionalProperties=False),
        "Devices": obj({"devices": array(obj({"ieee": {"type": "string"}, "name": {"type": "string"},
            "location_id": {"type": ["string", "null"]}, "registered": {"type": "boolean"},
            "profile":{"enum":[None,"SONOFF SNZB-02WD","SONOFF SNZB-02LD","SONOFF SNZB-02UL","SONOFF S60ZBTPG"]}, "discovery": {"enum": ["unknown", "partial"]}, "freshness_seconds": integer(60, 604800),
            "plug":{"anyOf":[{"type":"null"},ref("PlugView")]},"signal": signal,
            "measurements": array(measurement)}, ("ieee", "name", "location_id", "registered", "discovery", "freshness_seconds", "measurements")))}, ("devices",)),
        "History": obj({"items": array(obj({"id": integer(1), "received_at": {"type": "number"},
            "value": {"type": ["number", "boolean", "null"]}, "unit": {"type": "string"}, "quality": {"enum": ["valid", "invalid"]},
            **signal_metadata, "rssi": {"type": ["integer", "null"], "minimum": -128, "maximum": 126}},
            ("id", "received_at", "value", "unit", "quality")), maxItems=500),
            "next_cursor": {"type": ["string", "null"]}, "gaps_truncated": {"type": "boolean"}, "gaps": array(obj({"from": {"type": "number"},
                "to": {"type": "number"}, "reason": {"type": "string"}}, ("from", "to", "reason")), maxItems=500)}, ("items", "next_cursor", "gaps", "gaps_truncated")),
        "Error": obj({"error": obj({"code": {"type": "string"}, "message": {"type": "string"},
            "details": array(obj({"path": {"type": "string"}, "code": {"type": "string"}, "message": {"type": "string"}}, ("path", "code", "message")))},
            ("code", "message", "details")), "request_id": {"type": "string"}}, ("error", "request_id")),
        "Gateway": obj({"gateway_id":{"type":"string"},"network":{"type":"object"},"connected": {"type": "boolean"}, "ready": {"type": "boolean"}, "error": {"type": ["string", "null"]},
            "mode": {"enum": ["hardware", "simulator"]}}, ("connected", "error")),
        "Capabilities": obj({"api_version": {"const": "2"}, "widget_types": array({"enum": ["numeric", "chart"]}),
            "features": obj({k: {"const": True} for k in ("configuration", "history_query", "dashboard_layouts", "reporting_commissioning", "sensor_extensions", "user_profiles", "signal_history", "all_overview_layout", "smart_plugs", "grid_layouts", "system_dashboard")},
                ("configuration", "history_query", "dashboard_layouts", "reporting_commissioning", "sensor_extensions", "user_profiles", "signal_history", "all_overview_layout", "smart_plugs", "grid_layouts", "system_dashboard")),
            "limits": obj({k: ({"type": "array", "items": {"type": "integer"}} if k == "chart_ranges" else {"type": "integer"}) for k in capabilities_v2()["limits"]}, capabilities_v2()["limits"])},
            ("api_version", "widget_types", "features", "limits"))}
    policy = obj({"ieee":{"type":"string","pattern":"^[0-9a-f]{16}$"}, "endpoint":integer(1,240),
        "min_interval":integer(0,65534),"max_interval":integer(1,65534),
        "temperature_change":{"type":"number","minimum":0.01,"maximum":327.67,"multipleOf":0.01},
        "humidity_change":{"type":"number","minimum":0.01,"maximum":100,"multipleOf":0.01},
        "model_hint":{"enum":["","SONOFF SNZB-02WD","SONOFF SNZB-02LD","SONOFF SNZB-02UL"]}},
        ("ieee","endpoint","min_interval","max_interval","model_hint"),additionalProperties=False,
        anyOf=[{"required":["temperature_change"]},{"required":["humidity_change"]}])
    job = obj({"id":{"type":"string"},"ieee":{"type":"string"},"policy":dict(policy,additionalProperties=True),
        "state":{"enum":["queued","waiting","sending","verified","configured_unverified","failed","expired","cancelled"]},
        "step":integer(),"attempt":integer(0,3),"steps":array({"type":"object"},maxItems=11),
        "message":{"type":"string"},"results":array({"type":"object"},maxItems=32),
        "created_at":{"type":"number"},"expires_at":{"type":"number"}},
        ("id","ieee","policy","state","step","attempt","steps","message","results","created_at","expires_at"))
    definitions.update(CommissioningPolicy=policy,CommissioningJob=job,
        Commissioning=obj({"jobs":array(ref("CommissioningJob"),maxItems=50)},("jobs",)),
        CommissioningRequest={"oneOf":[ref("CommissioningPolicy"),obj({"ieee":{"type":"string","pattern":"^[0-9a-f]{16}$"},"action":{"const":"cancel"}},("ieee","action"),additionalProperties=False)]})
    display_fields={"temperature_units":{"enum":["celsius","fahrenheit"]},
        **{k:{"type":"number","minimum":low,"maximum":high,"multipleOf":.1} for k,low,high in (
            ("comfort_temperature_min",0,50),("comfort_temperature_max",0,50),("comfort_humidity_min",5,95),
            ("comfort_humidity_max",5,95),("temperature_calibration",-50,50),("humidity_calibration",-50,50))}}
    display_input=obj({"ieee":{"type":"string","pattern":"^[0-9a-f]{16}$"},"endpoint":integer(1,240),
        "settings":obj(display_fields,minProperties=1,maxProperties=7,additionalProperties=False)},("ieee","endpoint","settings"),additionalProperties=False)
    display_job=obj({"id":{"type":"string"},"ieee":{"type":"string"},"endpoint":integer(1,240),"settings":display_input['properties']['settings'],
        "state":{"enum":["queued","sending","waiting","failed","expired","cancelled","verified"]},"step":integer(0,14),"attempt":integer(0,3),
        "steps":array({"type":"object"},maxItems=14),"results":array({"type":"object"},maxItems=48),"message":{"type":"string"}},
        ("id","ieee","endpoint","settings","state","step","attempt","steps","results","message"))
    definitions.update(DisplayInput=display_input,DisplayJob=display_job,DisplayJobs=obj({"jobs":array(ref("DisplayJob"),maxItems=50)},("jobs",)),
        SensorProfiles=obj({"reference_revision":{"type":"string"},"reference_url":{"type":"string"},"profiles":array({"type":"object"},maxItems=3)},("reference_revision","reference_url","profiles")))
    paths = {"/api/v2/commissioning":{
        "get":{"operationId":"reporting_status","responses":{"200":response("Durable reporting jobs, observed identity and measurement origins",ref("Commissioning")),"401":response("Unauthorized",ref("Error"))}},
        "post":{"operationId":"configure_or_cancel_reporting","requestBody":{"required":True,"content":{"application/json":{"schema":ref("CommissioningRequest")}}},
            "responses":{"202":response("Queued, not remotely completed",ref("CommissioningJob")),"200":response("Cancelled; in-flight operations may complete",ref("CommissioningJob")),
                **{str(code):response(text,ref("Error")) for code,text in ((400,"Malformed body"),(401,"Unauthorized"),(404,"Unknown device/job"),(409,"Already running"),(413,"Body too large"),(422,"Invalid policy or endpoint"),(503,"Unsupported/offline gateway"))}}}}}

    cancel=obj({"ieee":{"type":"string","pattern":"^[0-9a-f]{16}$"},"action":{"const":"cancel"}},("ieee","action"),additionalProperties=False)
    display_responses={"202":response("Queued; not yet confirmed by device",ref("DisplayJob")),"200":response("Cancelled",ref("DisplayJob"))}
    display_responses.update({str(n):response("Invalid, unavailable or busy",ref("Error")) for n in (400,401,404,409,413,422,503)})
    paths['/api/v2/display']={"get":{"operationId":"display_jobs","responses":{"200":response("Persisted desired display settings and readback progress",ref("DisplayJobs")),"401":response("Unauthorized",ref("Error"))}}}
    paths['/api/v2/display']['post']={"operationId":"set_display_settings","requestBody":{"required":True,"content":{"application/json":{"schema":{"oneOf":[ref("DisplayInput"),cancel]}}}},"responses":display_responses}
    paths['/api/v2/sensor-profiles']={"get":{"operationId":"sensor_profiles","responses":{"200":response("Reference profiles; not paired devices",ref("SensorProfiles")),"401":response("Unauthorized",ref("Error"))}}}
    for route, name in (("configuration", "Configuration"), ("devices", "Devices"), ("history", "History"), ("gateway", "Gateway"), ("capabilities", "Capabilities")):
        paths['/api/v2/' + route] = {"get": {"operationId": "v2_" + route,
            "responses": {"200": response("Current " + route, ref(name)), "401": response("Unauthorized", ref("Error"))}}}
    paths['/api/v2/configuration']["get"]["responses"]["200"]["headers"] = {"ETag": {"schema": {"type": "string"}}}
    paths['/api/v2/configuration']["put"] = {"operationId": "replace_configuration",
        "parameters": [{"name": "If-Match", "in": "header", "required": True, "schema": {"type": "string"}}],
        "requestBody": {"required": True, "content": {"application/json": {"schema": ref("ConfigurationInput")}}},
        "responses": {"200": response("Saved configuration and new ETag", ref("Configuration")),
            **{str(code): response(message, ref("Error")) for code, message in ((400, "Malformed request"), (401, "Unauthorized"), (412, "Revision conflict"), (413, "Body too large"), (422, "Invalid configuration"), (428, "Revision required"))}}}
    history = paths['/api/v2/history']["get"]
    history["parameters"] = [{"name": key, "in": "query", "required": key not in ("limit", "cursor"),
        "schema": schema} for key, schema in (("ieee", {"type": "string", "pattern": "^[0-9a-fA-F]{16}$"}), ("endpoint", integer(1,240)),
            ("cluster", integer(0,65535)), ("attribute", integer(0,65535)), ("from", {"type": "number", "minimum": 0}),
            ("to", {"type": "number", "minimum": 0}), ("limit", integer(1,500)), ("cursor", {"type": "string"}))]
    history["responses"]["400"] = response("Invalid query or cursor", ref("Error"))
    paths['/api/v2/openapi.json'] = {"get": {"operationId": "v2_contract", "responses": {"200": response("This contract", {"type": "object"}), "401": response("Unauthorized", ref("Error"))}}}
    profile_id={"type":"string","pattern":"^(admin|p-[0-9a-f]{24})$"}
    definitions['UserProfile']=obj({'id':profile_id,'name':{'type':'string','minLength':1,'maxLength':80},'default':{'type':'boolean'}},('id','name','default'),additionalProperties=False)
    definitions['UserProfileInput']=obj({'name':{'type':'string','minLength':1,'maxLength':80}},('name',),additionalProperties=False)
    definitions['UserProfiles']=obj({'selected_profile':profile_id,'profiles':array(ref('UserProfile'),maxItems=20)},('selected_profile','profiles'),additionalProperties=False)
    errors={str(code):response(message,ref('Error')) for code,message in [(400,'Malformed request'),(401,'Dashboard token required'),(409,'Profile unavailable, duplicate name, default profile or limit'),(413,'Body too large'),(422,'Invalid profile') ]}
    selection=[{'name':'dashboard_profile','in':'cookie','schema':{'type':'string'},'description':'Session preference only; missing/invalid IDs default to Admin on reads.'},{'name':'X-Dashboard-Profile','in':'header','schema':{'type':'string'},'description':'Explicit request context, takes precedence over cookie; no authorisation effect.'}]
    body={'required':True,'content':{'application/json':{'schema':ref('UserProfileInput')}}}
    paths['/api/v2/profiles']={'get':{'operationId':'list_user_profiles','parameters':selection,'responses':{'200':response('Shared profile list and selected context',ref('UserProfiles')),**errors}},'post':{'operationId':'create_user_profile','requestBody':body,'responses':{'201':response('Created with empty layout and Celsius defaults',ref('UserProfile')),**errors}}}
    paths['/api/v2/profiles/{profile_id}']={'parameters':[{'name':'profile_id','in':'path','required':True,'schema':profile_id}], 'put':{'operationId':'rename_user_profile','requestBody':body,'responses':{'200':response('Renamed; stable ID retained',ref('UserProfile')),**errors}},'delete':{'operationId':'delete_user_profile','responses':{'200':response('Deleted presentation only',obj({'deleted':{'const':True}},('deleted',),additionalProperties=False)),**errors}}}
    for method in ['get','put']:
        op=paths['/api/v2/configuration'][method];op.setdefault('parameters',[]).extend(selection)
        op['responses']['200']['headers']={'ETag':{'schema':{'type':'string'}},'X-Dashboard-Profile':{'schema':profile_id}}
    paths['/api/v2/configuration']['put']['responses']['409']=response('Selected profile was removed; never save into fallback Admin',ref('Error'))
    from .plugs import profiles as plug_profiles
    plug_states=['queued','waiting','sending','verified','acknowledged_unverified','failed','uncertain','expired','cancelled']
    identity={'ieee':{'type':'string','pattern':'^[0-9a-f]{16}$'},'endpoint':integer(1,240)}
    variants=[]
    setting_variants={
        'relay':obj({'state':{'type':'boolean'}},('state',),additionalProperties=False),
        'startup_behavior':obj({'value':{'enum':['off','on','toggle','previous']}},('value',),additionalProperties=False),
        **{a:obj({'value':{'type':'boolean'}},('value',),additionalProperties=False) for a in ('network_indicator','outlet_protection')},
        'inching':obj({'enabled':{'type':'boolean'},'mode':{'enum':['on','off']},'seconds':{'type':'number','minimum':.5,'maximum':3599.5,'multipleOf':.5}},('enabled','mode','seconds'),additionalProperties=False)}
    limits={'max_current':{'type':'number','minimum':.1,'maximum':13,'multipleOf':.1},'max_power':{'type':'number','minimum':.1,'maximum':3250,'multipleOf':.1}}
    for name in ('min_current','max_voltage','min_voltage','min_power'):
        limits['enable_'+name]={'type':'boolean'}
        limits[name]={'type':'number','minimum':165 if 'voltage' in name else .1,'maximum':277 if 'voltage' in name else 13 if 'current' in name else 3250,'multipleOf':1 if 'voltage' in name else .1}
    setting_variants['protection']=obj(limits,('max_current','max_power'),additionalProperties=False,description='Complete composite; an enabled optional limit requires its value. Disabled values must be omitted. Minima must be below maxima. 13 A cap differs from upstream protocol maximum 14 A.')
    for action in ('read','commission'):setting_variants[action]=obj({},additionalProperties=False)
    for action,settings_schema in setting_variants.items():
        f={**identity,'action':{'const':action},'settings':settings_schema};variants.append(obj(f,f,additionalProperties=False))
    cancel_plug=obj({'job_id':{'type':'string'},'action':{'const':'cancel'}},('job_id','action'),additionalProperties=False)
    definitions.update(PlugInput={'oneOf':variants+[cancel_plug]},PlugProfiles={'const':plug_profiles()},
        PlugJob=obj({'id':{'type':'string'},**identity,'action':{'enum':list(setting_variants)},'state':{'enum':plug_states},'message':{'type':'string'},'step':integer(),'attempt':integer(0,3),'created_at':{'type':'number'},'expires_at':{'type':'number'},'steps':array({'type':'object'},maxItems=50),'results':array({'type':'object'},maxItems=96)},('id','ieee','endpoint','action','state','message','step','attempt','created_at','expires_at','steps','results')),
        PlugJobs=obj({'jobs':array(ref('PlugJob'),maxItems=100)},('jobs',)))
    definitions['PlugView']=obj({'controllable':{'type':'boolean'},'model':{'const':'SONOFF S60ZBTPG'},'hardware_status':{'const':'not_tested'},'endpoint':{'type':['integer','null'],'minimum':1,'maximum':240},
        'settings':obj({k:{'type':['object','null'],'description':'Actual readback/raw hex and source receipt timestamp; null until observed.'} for k in ('startup_behavior','network_indicator','outlet_protection','protection')},('startup_behavior','network_indicator','outlet_protection','protection')),
        'latest_job':{'anyOf':[{'type':'null'},obj({'id':{'type':'string'},'action':{'type':'string'},'state':{'enum':plug_states},'message':{'type':'string'},'settings':{'type':'object'},'step':integer(),'created_at':{'type':'number'}},('id','action','state','message','settings','step','created_at'))]},
        'effective_off':{'anyOf':[{'type':'null'},obj({'power_w':{'const':0},'current_a':{'const':0},'basis':{'const':'derived_from_confirmed_off'},'received_at':{'type':'number'}},('power_w','current_a','basis','received_at'))]},
        'energy_discontinuities':array(obj({'received_at':{'type':'number'},'reason':{'enum':['counter_decrease_reset_or_rollover','gateway_epoch_changed']}},('received_at','reason')),maxItems=50),
        'energy_policy':{'type':'string'},'routing':obj({'model_role':{'const':'router_capable'},'observed_mac_capability':{'type':['integer','null']},'full_function_device':{'type':['boolean','null']},'path_verification':{'const':'unverified'}},('model_role','observed_mac_capability','full_function_device','path_verification')),
        'capabilities':{'const':plug_profiles()['capabilities']}},('controllable','model','hardware_status','endpoint','settings','latest_job','effective_off','energy_discontinuities','energy_policy','routing','capabilities'))
    plug_errors={str(code):response(message,ref('Error')) for code,message in [(400,'Malformed input'),(401,'Token required'),(404,'Job not found'),(409,'Device operation active'),(413,'Body too large'),(422,'Unsupported device/settings'),(503,'Gateway upgrade/offline')]}
    paths['/api/v2/plug-profiles']={'get':{'operationId':'plug_capabilities','responses':{'200':response('Pinned model support and unresolved physical capabilities',ref('PlugProfiles')),'401':plug_errors['401']}}}
    paths['/api/v2/plugs']={'get':{'operationId':'plug_jobs','responses':{'200':response('Active jobs plus latest terminal jobs, at most 100 shared records; confirmed and uncertain states are distinct',ref('PlugJobs')),'401':plug_errors['401']}},
        'post':{'operationId':'request_plug_action','description':'Explicit operator action only. Writes submitted once; no optimistic relay state or uncertain replay. 202 is queued, not confirmed. Jobs/settings are shared across presentation profiles.','requestBody':{'required':True,'content':{'application/json':{'schema':ref('PlugInput')}}},'responses':{'202':response('Queued',ref('PlugJob')),'200':response('Cancelled; in-flight effects may remain',ref('PlugJob')),**plug_errors}}}
    system_obj = {"type": "object", "additionalProperties": True}
    definitions.update(SystemHost=system_obj, SystemDatabase=system_obj, PurgePreview=system_obj, PurgeResult=system_obj)
    paths['/api/v2/system'] = {"get": {"operationId": "system_host_health", "responses": {"200": response("Bounded host health snapshot", ref("SystemHost")), "401": response("Unauthorized", ref("Error"))}}}
    paths['/api/v2/system/database'] = {"get": {"operationId": "system_database_metrics", "responses": {"200": response("SQLite size, counts, retention and last integrity check", ref("SystemDatabase")), "401": response("Unauthorized", ref("Error"))}}}
    paths['/api/v2/system/database/check'] = {"post": {"operationId": "check_system_database", "description": "Explicit, bounded SQLite quick_check; not run during dashboard polling.", "responses": {"200": response("Integrity check result", system_obj), "401": response("Unauthorized", ref("Error")), "503": response("Database unavailable", ref("Error"))}}}
    paths['/api/v2/system/purge-preview'] = {"get": {"operationId": "preview_history_purge", "description": "Creates a five-minute in-memory preview for timestamped history older than 60 days.", "responses": {"200": response("Purge counts and confirmation token", ref("PurgePreview")), "401": response("Unauthorized", ref("Error"))}}}
    paths['/api/v2/system/purge'] = {"post": {"operationId": "purge_old_history", "description": "Deletes only timestamped telemetry tables represented by an unexpired preview in one transaction. Preserves registry, latest readings and configuration.", "requestBody": {"required": True, "content": {"application/json": {"schema": obj({"preview_id": {"type": "string", "minLength": 20, "maxLength": 100}}, ("preview_id",), additionalProperties=False)}}}, "responses": {"200": response("Deleted history row counts", ref("PurgeResult")), "401": response("Unauthorized", ref("Error")), "409": response("Preview expired", ref("Error")), "422": response("Invalid preview", ref("Error")), "503": response("Database unavailable", ref("Error"))}}}
    return {"openapi": "3.1.0", "info": {"title": "Zigbee dashboard v2 API", "version": "2.11.0"},
        "servers": [{"url": "/"}], "security": [{"bearerAuth": []}], "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}, "schemas": definitions}}
