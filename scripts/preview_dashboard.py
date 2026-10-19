#!/usr/bin/env python3
"""Serve the opt-in design preview against a PRIVATE COPY of the live database.

Only state/device GETs reach the running dashboard. Layout PUTs change the copy.
No poller, gateway client, radio commands or live configuration writes are started.
"""
import argparse
import hmac
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from http.server import ThreadingHTTPServer

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sbc.app import make_handler
from sbc.core import Store


def preview_handler(store, token, live, current_url):
    base = make_handler(store, SimpleNamespace(status={}), None, token)
    class Preview(base):
        def do_GET(self):
            if self.path in ('/api/v1/state','/api/v2/devices','/api/v2/commissioning','/api/v2/display','/api/v2/sensor-profiles','/api/v1/events') or urlsplit(self.path).path == '/api/v2/history':
                if not self.auth():return self.send(401, {'error':'token required'})
                try:
                    req=Request(live+self.path, headers={'Authorization':self.headers.get('Authorization',''),
                        'X-Dashboard-Profile':self.headers.get('X-Dashboard-Profile','admin')})
                    with urlopen(req,timeout=4) as response:
                        return self.send(200,json.load(response))
                except HTTPError as e:
                    return self.send(e.code,{'error':'Live dashboard request failed.'})
                except (URLError,TimeoutError,OSError):
                    return self.send(503,{'error':'Live dashboard unavailable; preview will retry.'})
            if self.path.startswith('/api/') and self.path not in ('/api/v2/configuration','/api/v2/profiles'):
                return self.send(404,{'error':'Not available in design preview.'})
            super().do_GET()
        def do_POST(self):self.send(405,{'error':'Device and profile actions are disabled in design preview.'})
        def do_DELETE(self):self.send(405,{'error':'Actions are disabled in design preview.'})
        def do_PUT(self):
            if self.path!='/api/v2/configuration':return self.send(405,{'error':'Only preview configuration can be saved.'})
            super().do_PUT()
    return Preview


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,help='Private snapshot, never the production database')
    parser.add_argument('--env-file',type=Path,required=True,help='Read only DASHBOARD_TOKEN from this private dotenv file')
    parser.add_argument('--live',default='http://127.0.0.1:8080')
    parser.add_argument('--current-url',default='http://127.0.0.1:8080')
    parser.add_argument('--bind',default='127.0.0.1');parser.add_argument('--port',type=int,default=8081)
    args=parser.parse_args()
    import shlex
    token=None
    for line in args.env_file.read_text().splitlines():
        if line.startswith('DASHBOARD_TOKEN='):
            values=shlex.split(line.split('=',1)[1]);token=values[0] if len(values)==1 else None
    if not token or len(token)<32:parser.error('A configured dashboard token is required.')
    if not Path(args.database).is_file():parser.error('Create a database snapshot before starting the preview.')
    # Fail if explicitly given the runtime DB configured alongside the token.
    for line in args.env_file.read_text().splitlines():
        if line.startswith('DB_PATH='):
            values=shlex.split(line.split('=',1)[1])
            if values:
                configured=Path(values[0]);configured=configured if configured.is_absolute() else args.env_file.parent/configured
                if configured.resolve()==Path(args.database).resolve():parser.error('Preview requires a separate database copy.')
    store=Store(args.database)
    server=ThreadingHTTPServer((args.bind,args.port),preview_handler(store,token,args.live.rstrip('/'),args.current_url))
    try:server.serve_forever()
    finally:server.server_close();store.close()

if __name__=='__main__':main()
