"""Implemented dashboard v2 contracts, separate from the board API."""
from .contracts import obj, array, integer, ref, response
from .dashboard import RANGES


def capabilities_v2():
    return {"api_version": "2", "widget_types": ["numeric", "chart"],
        "features": {"configuration": True, "history_query": True, "dashboard_layouts": True, "reporting_commissioning": True,"user_profiles":True,"sensor_extensions":True},
        "limits": {"configuration_bytes": 65536, "widgets": 100, "locations": 50,
            "device_overrides": 50, "history_page": 500, "history_days": 31,
            "history_retention_days": 30,"profiles":20,"profile_name_chars":80, "chart_ranges": list(RANGES)}}


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
    editable = obj({"locations": array(obj({"id": {"type": "string"}, "name": {"type": "string", "minLength": 1, "maxLength": 80}}, ("id", "name"), additionalProperties=False), maxItems=50),
        "devices": {"type": "object", "maxProperties": 50, "propertyNames": {"pattern": "^[0-9a-f]{16}$"}, "additionalProperties": settings},
        "dashboard": obj({"title": {"type": "string", "minLength": 1, "maxLength": 80},
            "temperature_unit": {"enum": ["celsius", "fahrenheit"]}, "widgets": array(widget, maxItems=100)},
            ("title", "temperature_unit", "widgets"), additionalProperties=False)},
        ("locations", "devices", "dashboard"), additionalProperties=False)
    measurement = obj({"endpoint": integer(1, 240), "cluster": integer(0, 65535), "attribute": integer(0, 65535),
        "origin":{"enum":["report","read_response","unknown"]}, "freshness_seconds":integer(60,604800),"low_battery":{"type":"boolean"}, "label": {"type": "string"}, "value": {"type": ["number", "boolean", "null"]}, "unit": {"type": "string"},
        "received_at": {"type": ["number", "null"]}, "quality": {"enum": ["valid", "invalid", "missing", "stale"]}},
        ("endpoint", "cluster", "attribute", "label", "value", "unit", "received_at", "quality"))
    definitions = {
        "ConfigurationInput": editable,
        "Configuration": obj({**editable["properties"], "schema_version": {"const": 1}, "revision": integer(1)},
            ("schema_version", "revision", "locations", "devices", "dashboard"), additionalProperties=False),
        "Devices": obj({"devices": array(obj({"ieee": {"type": "string"}, "name": {"type": "string"},
            "location_id": {"type": ["string", "null"]}, "registered": {"type": "boolean"},
            "profile":{"enum":[None,"SONOFF SNZB-02WD","SONOFF SNZB-02LD","SONOFF SNZB-02UL"]}, "discovery": {"enum": ["unknown", "partial"]}, "freshness_seconds": integer(60, 604800),
            "measurements": array(measurement)}, ("ieee", "name", "location_id", "registered", "discovery", "freshness_seconds", "measurements")))}, ("devices",)),
        "History": obj({"items": array(obj({"id": integer(1), "received_at": {"type": "number"},
            "value": {"type": ["number", "boolean", "null"]}, "unit": {"type": "string"}, "quality": {"enum": ["valid", "invalid"]}},
            ("id", "received_at", "value", "unit", "quality")), maxItems=500),
            "next_cursor": {"type": ["string", "null"]}, "gaps_truncated": {"type": "boolean"}, "gaps": array(obj({"from": {"type": "number"},
                "to": {"type": "number"}, "reason": {"type": "string"}}, ("from", "to", "reason")), maxItems=500)}, ("items", "next_cursor", "gaps", "gaps_truncated")),
        "Error": obj({"error": obj({"code": {"type": "string"}, "message": {"type": "string"},
            "details": array(obj({"path": {"type": "string"}, "code": {"type": "string"}, "message": {"type": "string"}}, ("path", "code", "message")))},
            ("code", "message", "details")), "request_id": {"type": "string"}}, ("error", "request_id")),
        "Gateway": obj({"connected": {"type": "boolean"}, "ready": {"type": "boolean"}, "error": {"type": ["string", "null"]},
            "mode": {"enum": ["hardware", "simulator"]}}, ("connected", "error")),
        "Capabilities": obj({"api_version": {"const": "2"}, "widget_types": array({"enum": ["numeric", "chart"]}),
            "features": obj({k: {"const": True} for k in ("configuration", "history_query", "dashboard_layouts", "reporting_commissioning", "sensor_extensions", "user_profiles")},
                ("configuration", "history_query", "dashboard_layouts", "reporting_commissioning", "sensor_extensions", "user_profiles")),
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
    return {"openapi": "3.1.0", "info": {"title": "Zigbee dashboard v2 API", "version": "2.4.0"},
        "servers": [{"url": "/"}], "security": [{"bearerAuth": []}], "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}, "schemas": definitions}}
