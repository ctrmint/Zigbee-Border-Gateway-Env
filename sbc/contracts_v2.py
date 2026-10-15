"""Implemented dashboard v2 contracts, separate from the board API."""
from .contracts import obj, array, integer, ref, response
from .dashboard import RANGES


def capabilities_v2():
    return {"api_version": "2", "widget_types": ["numeric", "chart"],
        "features": {"configuration": True, "history_query": True, "dashboard_layouts": True, "reporting_commissioning": True},
        "limits": {"configuration_bytes": 65536, "widgets": 100, "locations": 50,
            "device_overrides": 50, "history_page": 500, "history_days": 31,
            "history_retention_days": 30, "chart_ranges": list(RANGES)}}


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
        "origin":{"enum":["report","read_response","unknown"]}, "label": {"type": "string"}, "value": {"type": ["number", "boolean", "null"]}, "unit": {"type": "string"},
        "received_at": {"type": ["number", "null"]}, "quality": {"enum": ["valid", "invalid", "missing", "stale"]}},
        ("endpoint", "cluster", "attribute", "label", "value", "unit", "received_at", "quality"))
    definitions = {
        "ConfigurationInput": editable,
        "Configuration": obj({**editable["properties"], "schema_version": {"const": 1}, "revision": integer(1)},
            ("schema_version", "revision", "locations", "devices", "dashboard"), additionalProperties=False),
        "Devices": obj({"devices": array(obj({"ieee": {"type": "string"}, "name": {"type": "string"},
            "location_id": {"type": ["string", "null"]}, "registered": {"type": "boolean"},
            "discovery": {"enum": ["unknown", "partial"]}, "freshness_seconds": integer(60, 604800),
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
            "features": obj({k: {"const": True} for k in ("configuration", "history_query", "dashboard_layouts", "reporting_commissioning")},
                ("configuration", "history_query", "dashboard_layouts", "reporting_commissioning")),
            "limits": obj({k: ({"type": "array", "items": {"type": "integer"}} if k == "chart_ranges" else {"type": "integer"}) for k in capabilities_v2()["limits"]}, capabilities_v2()["limits"])},
            ("api_version", "widget_types", "features", "limits"))}
    policy = obj({"ieee":{"type":"string","pattern":"^[0-9a-f]{16}$"}, "endpoint":integer(1,240),
        "min_interval":integer(0,65534),"max_interval":integer(1,65534),
        "temperature_change":{"type":"number","minimum":0.01,"maximum":327.67,"multipleOf":0.01},
        "humidity_change":{"type":"number","minimum":0.01,"maximum":100,"multipleOf":0.01},
        "model_hint":{"enum":["","SONOFF SNZB-02WD","SONOFF SNZB-02LD"]}},
        ("ieee","endpoint","min_interval","max_interval","model_hint"),additionalProperties=False,
        anyOf=[{"required":["temperature_change"]},{"required":["humidity_change"]}])
    job = obj({"id":{"type":"string"},"ieee":{"type":"string"},"policy":dict(policy,additionalProperties=True),
        "state":{"enum":["queued","waiting","sending","verified","configured_unverified","failed","expired","cancelled"]},
        "step":integer(),"attempt":integer(0,3),"steps":array({"type":"object"},maxItems=7),
        "message":{"type":"string"},"results":array({"type":"object"},maxItems=32),
        "created_at":{"type":"number"},"expires_at":{"type":"number"}},
        ("id","ieee","policy","state","step","attempt","steps","message","results","created_at","expires_at"))
    definitions.update(CommissioningPolicy=policy,CommissioningJob=job,
        Commissioning=obj({"jobs":array(ref("CommissioningJob"),maxItems=50)},("jobs",)),
        CommissioningRequest={"oneOf":[ref("CommissioningPolicy"),obj({"ieee":{"type":"string","pattern":"^[0-9a-f]{16}$"},"action":{"const":"cancel"}},("ieee","action"),additionalProperties=False)]})
    paths = {"/api/v2/commissioning":{
        "get":{"operationId":"reporting_status","responses":{"200":response("Durable reporting jobs, observed identity and measurement origins",ref("Commissioning")),"401":response("Unauthorized",ref("Error"))}},
        "post":{"operationId":"configure_or_cancel_reporting","requestBody":{"required":True,"content":{"application/json":{"schema":ref("CommissioningRequest")}}},
            "responses":{"202":response("Queued, not remotely completed",ref("CommissioningJob")),"200":response("Cancelled; in-flight operations may complete",ref("CommissioningJob")),
                **{str(code):response(text,ref("Error")) for code,text in ((400,"Malformed body"),(401,"Unauthorized"),(404,"Unknown device/job"),(409,"Already running"),(413,"Body too large"),(422,"Invalid policy or endpoint"),(503,"Unsupported/offline gateway"))}}}}}

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
    return {"openapi": "3.1.0", "info": {"title": "Zigbee dashboard v2 API", "version": "2.1.1"},
        "servers": [{"url": "/"}], "security": [{"bearerAuth": []}], "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}, "schemas": definitions}}
