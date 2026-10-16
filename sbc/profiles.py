"""Convenience profiles: presentation state, never an identity/security boundary."""
import json
import re
import secrets
import unicodedata
from http.cookies import SimpleCookie, CookieError

COOKIE = 'dashboard_profile'
PROFILE_ID = re.compile(r'(?:admin|p-[0-9a-f]{24})\Z')


def requested_profile(headers):
    explicit = headers.get('X-Dashboard-Profile')
    if explicit is not None:
        return explicit if len(explicit) <= 64 else ''
    try:
        cookie = SimpleCookie()
        cookie.load(headers.get('Cookie', '')[:8192])
        return cookie[COOKIE].value if COOKIE in cookie else 'admin'
    except (CookieError, ValueError):
        return ''


class ProfilesStore:
    def _init_profiles(self):
        self.db.execute('''CREATE TABLE IF NOT EXISTS user_profiles(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT UNIQUE NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1, data TEXT)''')
        self.db.execute("INSERT OR IGNORE INTO user_profiles(id,name,name_key) VALUES('admin','Admin','admin')")
        self.db.commit()

    def resolve_profile(self, requested):
        with self.lock:
            if isinstance(requested, str) and PROFILE_ID.fullmatch(requested) and self.db.execute('SELECT 1 FROM user_profiles WHERE id=?',(requested,)).fetchone():
                return requested
            return 'admin'

    def _require_profile(self, profile):
        from .dashboard import DashboardError
        if self.resolve_profile(profile) != profile:
            raise DashboardError('Profile no longer available. Select a profile again.',409,'profile_unavailable')

    def profiles_document(self, selected='admin'):
        with self.lock:
            return {'selected_profile':self.resolve_profile(selected), 'profiles':[
                {'id':r[0],'name':r[1],'default':r[0]=='admin'} for r in self.db.execute("SELECT id,name FROM user_profiles ORDER BY id!='admin',name_key,id")]}

    def save_profile(self, body, profile=None):
        from .dashboard import DashboardError, text
        if not isinstance(body,dict) or set(body)!={'name'}:
            raise DashboardError('Provide only a profile name.')
        name=text(body['name'],'name');key=unicodedata.normalize('NFKC',name).casefold()
        with self.lock,self.db:
            if profile is not None:
                self._require_profile(profile)
                if profile=='admin':raise DashboardError('Admin is the permanent default profile.',409,'default_profile')
            if self.db.execute('SELECT 1 FROM user_profiles WHERE name_key=? AND id!=?',(key,profile or '')).fetchone():
                raise DashboardError('A profile with that name already exists.',409,'duplicate_profile')
            if profile is None:
                if self.db.execute('SELECT COUNT(*) FROM user_profiles').fetchone()[0]>=20:
                    raise DashboardError('Profile limit of 20 reached.',409,'profile_limit')
                profile='p-'+secrets.token_hex(12)
                data=json.dumps({'title':'Home','temperature_unit':'celsius','widgets':[]})
                self.db.execute('INSERT INTO user_profiles(id,name,name_key,data) VALUES(?,?,?,?)',(profile,name,key,data))
            else:self.db.execute('UPDATE user_profiles SET name=?,name_key=? WHERE id=?',(name,key,profile))
            return {'id':profile,'name':name,'default':False}

    def delete_profile(self, profile):
        from .dashboard import DashboardError
        with self.lock,self.db:
            self._require_profile(profile)
            if profile=='admin':raise DashboardError('Admin is the permanent default profile.',409,'default_profile')
            self.db.execute('DELETE FROM user_profiles WHERE id=?',(profile,))

    def _profile_configuration(self, profile):
        self._require_profile(profile)
        if profile=='admin':return self.db.execute('SELECT revision,data FROM dashboard_config WHERE id=1').fetchone()
        return self.db.execute('SELECT revision,data FROM user_profiles WHERE id=?',(profile,)).fetchone()

    def configuration_etag(self, profile='admin'):
        with self.lock:
            revision,_=self._profile_configuration(profile)
            return f'"configuration-{revision}"' if profile=='admin' else f'"configuration-{profile}-{revision}"'
