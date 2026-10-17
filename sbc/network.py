"""Authenticated gateway HTTP and bounded, identity-pinned LAN rediscovery."""
import hashlib
import hmac
import ipaddress
import json
import secrets
import socket
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

DISCOVERY_PORT = 39128


def sample_received(event, receipt):
    estimate=event.get('observed_at_estimate')
    return estimate if type(estimate) in (int,float) and 0<=estimate<=receipt else receipt


def discovery_response(packet, nonce, identity, token, address):
    try:
        d=json.loads(packet)
        if d['nonce']!=nonce or d['gateway_id']!=identity or type(d['port']) is not int or not 1<=d['port']<=65535:return None
        if not ipaddress.IPv4Address(address).is_private:return None
        expected=hmac.new(token.encode(),f"{nonce}|{identity}|{d['port']}".encode(),hashlib.sha256).hexdigest()
        if not isinstance(d.get('proof'),str) or not hmac.compare_digest(d['proof'],expected):return None
        return f"http://{address}:{d['port']}"
    except (ValueError,KeyError,TypeError,UnicodeError):return None


class Gateway:
    def __init__(self,url,token):
        self.url,self.token=url.rstrip('/'),token
        self.configured_url=self.url;self.identity=None;self.store=None
        self._lock=threading.RLock();self._next_discovery=0;self._saved_binding=None
        self._key=hashlib.sha256((self.configured_url+'\0'+token).encode()).hexdigest()

    def attach_store(self,store):
        self.store=store
        with store.lock:
            row=store.db.execute('SELECT identity,url FROM gateway_bindings WHERE config_key=?',(self._key,)).fetchone()
        if row:self.identity,self.url=row;self._saved_binding=(self.identity,self.url)

    def _remember(self,identity):
        if not isinstance(identity,str) or len(identity)!=12 or any(c not in '0123456789abcdef' for c in identity):return
        if self.identity and identity!=self.identity:raise ValueError('Gateway identity changed')
        self.identity=identity
        if self.store and self._saved_binding!=(identity,self.url):
            with self.store.lock,self.store.db:
                self.store.db.execute('INSERT INTO gateway_bindings VALUES(?,?,?) ON CONFLICT(config_key) DO UPDATE SET identity=excluded.identity,url=excluded.url',(self._key,identity,self.url))
            self._saved_binding=(identity,self.url)

    def _discover(self):
        if not self.identity or time.monotonic()<self._next_discovery or urllib.parse.urlsplit(self.url).scheme!='http':return None
        self._next_discovery=time.monotonic()+30
        host=urllib.parse.urlsplit(self.url).hostname
        try:
            if ipaddress.ip_address(host).is_loopback:return None
        except ValueError:pass
        nonce=secrets.token_hex(16);proof=hmac.new(self.token.encode(),('discover|'+nonce).encode(),hashlib.sha256).hexdigest();message=json.dumps(dict(op='discover_gateway',nonce=nonce,proof=proof)).encode()
        targets={'255.255.255.255'}
        try:targets.add(str(ipaddress.ip_network(host+'/24',strict=False).broadcast_address))
        except ValueError:pass
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1);sock.settimeout(.25)
            for target in targets:
                try:sock.sendto(message,(target,DISCOVERY_PORT))
                except OSError:pass
            deadline=time.monotonic()+1.5
            while time.monotonic()<deadline:
                try:packet,peer=sock.recvfrom(512)
                except socket.timeout:continue
                candidate=discovery_response(packet,nonce,self.identity,self.token,peer[0])
                if candidate:return candidate
        return None

    def _http(self,path,data=None):
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,
            headers={'Authorization':'Bearer '+self.token,'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)

    def request(self,path,data=None):
        with self._lock:
            try:
                result=self._http(path,data)
                if path=='/api/v1/health' and self.identity and result.get('gateway_id')!=self.identity:
                    raise urllib.error.URLError('Gateway identity mismatch')
            except (urllib.error.URLError,OSError) as error:
                # A pinned address may now belong to a different HTTP device.
                if isinstance(error,urllib.error.HTTPError) and (not self.identity or error.code not in (401,404)):raise
                candidate=self._discover()
                if not candidate:raise
                previous=self.url;self.url=candidate
                try:
                    health=self._http('/api/v1/health')
                    if health.get('gateway_id')!=self.identity:raise ValueError('Discovery identity mismatch')
                    self._remember(self.identity)
                except Exception:self.url=previous;raise
                # An uncertain POST may have executed: only GET requests are retried.
                if data is not None:raise
                result=health if path=='/api/v1/health' else self._http(path)
            if path=='/api/v1/health':self._remember(result.get('gateway_id'))
            return result
