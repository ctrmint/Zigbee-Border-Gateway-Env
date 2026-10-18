"""Executable API descriptions; runtime needs only the Python standard library."""
import argparse
import json
from pathlib import Path

from .core import OPS

CONTRACT_VERSION = "1.7.0"


def ref(name):
    return {"$ref": f"#/components/schemas/{name}"}


def obj(properties, required=(), **options):
    return dict(type="object", properties=properties, required=list(required), **options)


def array(items, **options):
    return dict(type="array", items=items, **options)


def integer(lo=0, hi=None):
    return dict(type="integer", minimum=lo, **({"maximum": hi} if hi is not None else {}))


def schemas(strict_commands):
    ieee = {"type": "string", "pattern": "^[0-9a-fA-F]{16}$"}
    timestamp = {"type": "number", "description": "Unix seconds when received by the SBC, not device observation time."}
    base_event = dict(type={"type": "string", "description": "Unknown future event types must be retained and ignored by projections."},
                      seq=integer(), uptime_ms=integer(), nwk=integer(0, 65535), ieee=ieee)
    commands = []
    for op in sorted(OPS):
        fields = {"op": {"const": op}}
        if op == "sync_clock":
            fields.update(unix_time=integer(1577836800,4102444800),utc_offset=integer(-50400,50400))
        elif op == "permit_join":
            fields["seconds"] = integer(0, 180)
        else:
            fields["ieee"] = ieee
            if op != "discover":
                fields["endpoint"] = integer(1, 240)
            if op == "read":
                fields.update(cluster=integer(0, 65535), attribute=integer(0, 65535))
            if op in ('bind','configure_reporting','read_reporting','reporting_window','write_display','read_display'):
                fields['request_id']={'type':'string','pattern':'^[0-9a-f-]{36}$'}
                if op=='reporting_window':fields['seconds']=integer(0,120)
                else:
                    fields['cluster']={'enum':[1,6,32,1026,1029] if op=='bind' else [64529] if op in ('write_display','read_display') else [1,1026,1029]}
                    if op!='bind':fields['attribute']={'enum':[0,32,33]} if op in ('configure_reporting','read_reporting') else {'enum':[3,4,5,6,7,8195,8196]}
                    if op=='write_display':fields['value']=integer(-5000,9500)
                    if op=='configure_reporting':fields.update(min_interval=integer(0,65534),max_interval=integer(1,65534),reportable_change=integer(1,32767))
            if op == "on_off":
                fields["state"] = {"type": "boolean"}
        commands.append(obj(fields, fields, additionalProperties=not strict_commands))
    if not strict_commands:
        from .plugs import READS,WRITES,REPORTS
        base={'ieee':ieee,'endpoint':integer(1,240),'request_id':{'type':'string','pattern':'^[0-9a-f-]{36}$'}}
        for op in ('plug_read','plug_write','plug_relay','plug_inching','plug_bind','plug_configure','plug_read_reporting'):
            keys=READS if op=='plug_read' else WRITES if op=='plug_write' else REPORTS if op in ('plug_configure','plug_read_reporting') else [(6,0),(1794,0),(64529,0)] if op=='plug_bind' else [(6,0)] if op=='plug_relay' else [(64529,0)]
            if op=='plug_write':keys=[*keys,(64529,0x7003)]
            for c,a in keys:
                f=dict(base,op={'const':op},cluster={'const':c},attribute={'const':a})
                if op in ('plug_inching','plug_write') and (op=='plug_inching' or a==0x7003):f['payload']={'type':'string','pattern':'^[0-9a-f]{'+('22' if op=='plug_inching' else '26,58')+'}$','description':'Validated model-specific payload; no arbitrary vendor writes.'}
                elif op in ('plug_write','plug_relay'):f['value']={'enum':[0,1,2,255] if a==0x4003 else [0,1]}
                commands.append(obj(f,f,additionalProperties=False))
    return {
        "Command": {"oneOf": commands, "description": "A request is at most 512 UTF-8 bytes. 202 confirms stack acceptance only."},
        "CommandResult": obj({"accepted": {"type": "boolean"}, "stack_result": {"type": "integer"}}, ("accepted", "stack_result")),
        "Error": obj({"error": {"type": "string"}}, ("error",)),
        "RegistryDevice": obj({"ieee": ieee, "nwk": integer(0, 65535), "active": {"type": "boolean", "description": "Registered, not proof of reachability."}}, ("ieee", "nwk", "active")),
        "Registry": obj({"boot_id": {"type": "string"}, "devices": array(ref("RegistryDevice"), maxItems=50)}, ("boot_id", "devices")),
        "Event": obj({**base_event,
            "endpoint": integer(1, 240), "cluster": integer(0, 65535), "attribute": integer(0, 65535),
            "raw_hex":{"type":"string","pattern":"^[0-9a-f]{0,58}$"},"data_type": integer(0, 255), "raw": {"type": ["number", "string", "boolean", "null"]},
            "rssi": {"type": "integer"}, "ok": {"type": "boolean"},
            "profile_id": integer(0, 65535), "device_id": integer(0, 65535),
            "input_clusters": array(integer(0, 65535)), "output_clusters": array(integer(0, 65535)),
            "status": integer(-2147483648, 2147483647), "tsn": integer(0, 255), "capability": integer(0, 255),
            "origin": {"enum": ["report","read_response","unknown"]},
            "request_id": {"type":"string"}, "operation":{"type":"string"}, "phase":{"enum":["response","transport_error","timeout"]},
            "min_interval":integer(0,65535),"max_interval":integer(0,65535),"reportable_change":integer(0,65535),
            "unsupported_type": {"type": "boolean"}}, ("type", "seq", "uptime_ms", "nwk"),
            allOf=[
                {"if": {"properties": {"type": {"const": "attribute"}}},
                 "then": {"required": ["endpoint", "cluster", "attribute", "data_type", "rssi"]}},
                {"if": {"properties": {"type": {"const": "discovery"}}},
                 "then": {"required": ["ok"]}},
                {"if": {"properties": {"type": {"const": "endpoint"}}},
                 "then": {"required": ["endpoint", "ok"], "allOf": [
                     {"if": {"properties": {"ok": {"const": True}}}, "then": {
                         "required": ["profile_id", "device_id", "input_clusters", "output_clusters"]}}]}},
                {"if": {"properties": {"type": {"const": "zcl_response"}}},
                 "then": {"required": ["status", "tsn"]}},
            ]),
        "EventBatch": obj({"boot_id": {"type": "string"}, "gap": {"type": "boolean"},
            "events": array(ref("Event"), maxItems=16), "next_seq": integer(), "latest_seq": integer()},
            ("boot_id", "gap", "events", "next_seq", "latest_seq")),
        "Health": obj({"gateway_id":{"type":"string","pattern":"^[0-9a-f]{12}$"},"network":{"type":"object","description":"Wi-Fi recovery counters, link/IP/API state, backoff/progress times, disconnect/reboot reasons and opt-in test state. No credentials."},"boot_id": {"type": "string"}, "ready": {"type": "boolean"},
            "mode": {"enum": ["hardware", "simulator"]}, "reporting_commissioning":{"type":"boolean"},"plug_extensions":{"type":"boolean"},"sensor_extensions":{"type":"boolean"},"time_server_valid":{"type":"boolean"}, "join_seconds": integer(0, 180),
            "latest_seq": integer(), "dropped_events": integer(), "uptime_ms": integer(),
            "pan_id": integer(0, 65535), "channel": dict(integer(0, 26), description="Zero before formation; 11–26 when ready.")},
            ("boot_id", "ready", "mode", "join_seconds", "latest_seq", "dropped_events")),
        "GatewayStatus": obj({"gateway_id":{"type":"string"},"network":{"type":"object"},"connected": {"type": "boolean"}, "error": {"type": ["string", "null"]},
            "gap": {"type": "boolean"}, "last_poll": timestamp,
            "boot_id": {"type": "string"}, "ready": {"type": "boolean"},
                "mode": {"enum": ["hardware", "simulator"]}, "reporting_commissioning":{"type":"boolean"},"plug_extensions":{"type":"boolean"},"sensor_extensions":{"type":"boolean"},"time_server_valid":{"type":"boolean"}, "join_seconds": integer(0, 180),
                "latest_seq": integer(), "dropped_events": integer(), "uptime_ms": integer(),
                "pan_id": integer(0, 65535), "channel": integer(0, 26)}, ("connected", "error", "gap")),
        "Endpoint": obj({"profile_id": integer(0, 65535), "device_id": integer(0, 65535),
            "input_clusters": array(integer(0, 65535)), "output_clusters": array(integer(0, 65535))},
            ("profile_id", "device_id", "input_clusters", "output_clusters")),
        "Attribute": {"allOf": [ref("Event"), obj({"received": timestamp,
            "value": {"type": ["number", "boolean", "null"]}, "unit": {"enum": ["°C", "%", "on/off", "V", None]}},
            ("received", "value", "unit"))]},
        "Device": obj({"ieee": ieee, "nwk": integer(0, 65535), "active": {"type": "boolean"},
            "location_id": {"type": ["string", "null"], "format": "uuid"},
            "location_name": {"type": ["string", "null"]},
            "last_seen": timestamp, "endpoints": {"type": "object", "additionalProperties": ref("Endpoint")},
            "attributes": {"type": "object", "additionalProperties": ref("Attribute")}}, ("ieee", "endpoints", "attributes")),
        "State": obj({"gateway": ref("GatewayStatus"), "devices": array(ref("Device")), "locations": array(ref("Location"), maxItems=50)}, ("gateway", "devices", "locations")),
        "Location": obj({"id": {"type": "string", "format": "uuid"}, "name": {"type": "string", "minLength": 1, "maxLength": 80},
            "device_count": integer()}, ("id", "name", "device_count")),
        "LocationList": obj({"locations": array(ref("Location"), maxItems=50)}, ("locations",)),
        "LocationInput": obj({"name": {"type": "string", "minLength": 1, "maxLength": 80,
            "description": "Trimmed, visible, single-line name. Unique after Unicode normalization and case folding."}}, ("name",), additionalProperties=False),
        "LocationAssignment": obj({"location_id": {"type": ["string", "null"], "format": "uuid"}}, ("location_id",), additionalProperties=False),
        "LocationAssignmentResult": obj({"ieee": ieee, "location_id": {"type": ["string", "null"], "format": "uuid"}}, ("ieee", "location_id")),
        "Deleted": obj({"deleted": {"const": True}}, ("deleted",)),
        "HistoryEvent": {"allOf": [ref("Event"), obj({"received": timestamp, "boot_id": {"type": "string"}}, ("received", "boot_id"))]},
        "History": obj({"events": array(ref("HistoryEvent"), maxItems=100)}, ("events",)),
        "Capabilities": obj({"api_version": {"const": CONTRACT_VERSION}, "gateway_api_version": {"const": "1"},
            "operations": array({"enum": sorted(OPS)}, uniqueItems=True),
            "features": obj({key: {"type": "boolean"} for key in
                ("locations", "device_configuration", "dashboard_layouts", "history_query", "command_tracking", "event_stream")},
                ("locations", "device_configuration", "dashboard_layouts", "history_query", "command_tracking", "event_stream")),
            "limits": obj({"command_bytes": {"const": 512}, "pairing_seconds": {"const": 180},
                "history_events": {"const": 100}, "locations": {"const": 50}, "location_name_characters": {"const": 80}},
                ("command_bytes", "pairing_seconds", "history_events", "locations", "location_name_characters")),
            "contracts": obj({"dashboard": {"const": "/api/v1/openapi.json"}, "dashboard_v2": {"const": "/api/v2/openapi.json"}}, ("dashboard", "dashboard_v2"))},
            ("api_version", "gateway_api_version", "operations", "features", "limits", "contracts")),
    }


def capabilities():
    """SBC support, independent of gateway readiness and per-device support."""
    return {"api_version": CONTRACT_VERSION, "gateway_api_version": "1", "operations": sorted(OPS),
            "features": {"locations": True, "device_configuration": True, "dashboard_layouts": True, "history_query": True, "command_tracking": False, "event_stream": False},
            "limits": {"command_bytes": 512, "pairing_seconds": 180, "history_events": 100, "locations": 50, "location_name_characters": 80},
            "contracts": {"dashboard": "/api/v1/openapi.json", "dashboard_v2": "/api/v2/openapi.json"}}


def response(description, schema, mime="application/json"):
    return {"description": description, "content": {mime: {"schema": schema}}}


def referenced_schemas(paths, definitions):
    """Include only definitions reachable from this service's routes."""
    selected = {}

    def visit(value):
        if isinstance(value, dict):
            target = value.get("$ref", "")
            if target.startswith("#/components/schemas/"):
                name = target.rsplit("/", 1)[1]
                if name not in selected:
                    selected[name] = definitions[name]
                    visit(definitions[name])
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(paths)
    return selected


def contract(service="dashboard"):
    if service not in ("dashboard", "gateway"):
        raise ValueError("unknown API service")
    board = service == "gateway"
    error = {"type": "string"} if board else ref("Error")
    error_mime = "text/html" if board else "application/json"
    unauthorized = response("Missing or invalid bearer token", error, error_mime)
    paths = {}
    routes = {"health": "Health", "devices": "Registry", "events": "EventBatch"} if board else {
        "state": "State", "events": "History", "locations": "LocationList", "capabilities": "Capabilities", "openapi.json": None}
    for route, schema in routes.items():
        op = {"operationId": service + "_" + route.replace(".", "_"),
              "responses": {"200": response("Current " + route, ref(schema) if schema else {"type": "object"}), "401": unauthorized}}
        if board and route == "events":
            op["responses"]["400"] = response("Invalid or ambiguous event cursor query", error, error_mime)
            op["parameters"] = [{"name": "after", "in": "query", "required": False,
                "description": "Single decimal cursor; no additional query parameters. Reset to zero when boot_id changes (restart or sequence epoch rollover).",
                "schema": dict(integer(0, 4294967295), default=0)}]
        paths["/api/v1/" + route] = {"get": op}
    busy = {"oneOf": [ref("CommandResult"), ref("Error")]}
    paths["/api/v1/commands"] = {"post": {
        "operationId": service + "_command", "description": "No automatic retries. A timeout can mean the request executed. No delivery or state confirmation.",
        "requestBody": {"required": True, "content": {"application/json": {"schema": ref("Command")}}},
        "responses": {"202": response("Accepted by the Zigbee stack", ref("CommandResult")),
            "400": response("Invalid command" + (" or unknown/inactive device" if board else ""), error, error_mime),
            "401": unauthorized, "503": response("Offline, not ready, busy, or stack rejected", busy),
            **({"502": response("Upstream failure; execution may have occurred", ref("Error"))} if not board else {})}}}
    if not board:
        config_errors = {"400": response("Invalid configuration", ref("Error")), "401": unauthorized,
                         "404": response("Unknown location or device", ref("Error")),
                         "409": response("Duplicate name, location limit, or location still assigned", ref("Error"))}
        def mutation(name, input_schema, output_schema, status="200"):
            operation = {"operationId": name, "responses": {status: response("Saved configuration", ref(output_schema)), **config_errors}}
            if input_schema:
                operation["requestBody"] = {"required": True, "content": {"application/json": {"schema": ref(input_schema)}}}
            return operation
        paths["/api/v1/locations"]["post"] = mutation("create_location", "LocationInput", "Location", "201")
        paths["/api/v1/locations/{id}"] = {
            "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "put": mutation("rename_location", "LocationInput", "Location"),
            "delete": mutation("delete_empty_location", None, "Deleted")}
        paths["/api/v1/devices/{ieee}/location"] = {
            "parameters": [{"name": "ieee", "in": "path", "required": True, "schema": {"type": "string", "pattern": "^[0-9a-fA-F]{16}$"}}],
            "put": mutation("assign_device_location", "LocationAssignment", "LocationAssignmentResult")}
    if board:
        paths['/api/v1/network-test']={"post":{"operationId":"bounded_network_outage_test",
            "description":"Available only when built with CONFIG_GW_NETWORK_TEST. Temporarily uses an unavailable SSID, restores configured credentials autonomously. Does not reset Zigbee. No automatic use by the dashboard.",
            "requestBody":{"required":True,"content":{"application/json":{"schema":obj({"seconds":integer(1,300)},("seconds",),additionalProperties=False)}}},
            "responses":{"202":response("Accepted; expect temporary network loss",obj({"accepted":{"const":True}},("accepted",))),"400":response("Invalid request or test already active",error,error_mime),"401":unauthorized,"404":response("Test feature disabled in this build",error,error_mime)}}}
    return {"openapi": "3.1.0", "info": {"title": "Zigbee " + service + " API", "version": CONTRACT_VERSION,
        "description": "Implemented v1 API. Additive response fields are allowed. Proposed dashboard configuration APIs are documented separately."},
        "servers": [{"url": "/"}] if not board else [{"url": "http://{gateway_host}",
            "variables": {"gateway_host": {"default": "192.168.1.100", "description": "Replace with the board's reserved LAN address."}}}],
        "security": [{"bearerAuth": []}], "paths": paths,
        "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer",
            "description": "GATEWAY_TOKEN" if board else "DASHBOARD_TOKEN"}},
            "schemas": referenced_schemas(paths, schemas(not board))}}


def main():
    parser = argparse.ArgumentParser(description="Export or verify the checked-in OpenAPI contracts")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1] / "docs" / "api"
    from .contracts_v2 import contract_v2
    documents = {"dashboard-v1": contract(), "gateway-v1": contract("gateway"), "dashboard-v2": contract_v2()}
    for service, document in documents.items():
        path = root / (service + ".openapi.json")
        content = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != content:
                raise SystemExit(f"Contract out of date: {path}; run python3 -m sbc.contracts")
        else:
            root.mkdir(parents=True, exist_ok=True)
            path.write_text(content)


if __name__ == "__main__":
    main()
