"""Passive coordinator RSSI samples, correlated with their original gateway events."""
import json
import time
from .network import sample_received

# Dashboard-only source identifier; never transmitted as a Zigbee cluster command.
SIGNAL_CLUSTER = 65535
SIGNAL_RETENTION_DAYS = 60


def valid_rssi(value):
    # Signed int8 radio RSSI; 127 is the conventional unavailable sentinel.
    return type(value) is int and -128 <= value <= 126


class SignalStore:
    def _init_signal(self):
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS signal_samples(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                boot TEXT NOT NULL, seq INTEGER NOT NULL, ieee TEXT NOT NULL,
                received REAL NOT NULL, rssi INTEGER NOT NULL,
                endpoint INTEGER, cluster INTEGER, attribute INTEGER,
                event_type TEXT NOT NULL, origin TEXT,
                UNIQUE(boot,seq));
            CREATE INDEX IF NOT EXISTS signal_source_time ON signal_samples(ieee,received,id);
            CREATE INDEX IF NOT EXISTS signal_retention_time ON signal_samples(received);
            CREATE TABLE IF NOT EXISTS signal_latest(ieee TEXT PRIMARY KEY, data TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS signal_migration(id INTEGER PRIMARY KEY CHECK(id=1));
        ''')
        with self.db:
            if not self.db.execute('SELECT 1 FROM signal_migration').fetchone():
                for boot, received, data in self.db.execute('SELECT boot,received,data FROM events ORDER BY received,seq'):
                    self._record_signal(boot, json.loads(data), received)
                self.db.execute('INSERT INTO signal_migration VALUES(1)')
            self._prune_signal(time.time())

    def _record_signal(self, boot, event, received):
        if not event.get('ieee') or not valid_rssi(event.get('rssi')):
            return
        received = sample_received(event, received)
        sample = dict(boot_id=boot, seq=event['seq'], ieee=event['ieee'].lower(),
                      received_at=received, value=event['rssi'], unit='dBm',
                      source_endpoint=event.get('endpoint'), source_cluster=event.get('cluster'),
                      source_attribute=event.get('attribute'), event_type=event['type'],
                      origin=event.get('origin', 'unknown'))
        self.db.execute('''INSERT OR IGNORE INTO signal_samples
            (boot,seq,ieee,received,rssi,endpoint,cluster,attribute,event_type,origin)
            VALUES(?,?,?,?,?,?,?,?,?,?)''', (boot,event['seq'],sample['ieee'],received,event['rssi'],
                sample['source_endpoint'],sample['source_cluster'],sample['source_attribute'],event['type'],sample['origin']))
        old = self.db.execute('SELECT data FROM signal_latest WHERE ieee=?',(sample['ieee'],)).fetchone()
        if not old or json.loads(old[0])['received_at'] <= received:
            self.db.execute('INSERT OR REPLACE INTO signal_latest VALUES(?,?)',(sample['ieee'],json.dumps(sample)))

    def _prune_signal(self, now, days=SIGNAL_RETENTION_DAYS):
        self.db.execute('DELETE FROM signal_samples WHERE received < ?', (now-days*86400,))

    def signal_view(self, ieee, freshness, now):
        row = self.db.execute('SELECT data FROM signal_latest WHERE ieee=?',(ieee,)).fetchone()
        sample = json.loads(row[0]) if row else dict(value=None,received_at=None,unit='dBm')
        return dict(sample, label='Signal strength', endpoint=1, cluster=SIGNAL_CLUSTER, attribute=0,
                    freshness_seconds=freshness,
                    quality='missing' if row is None else 'stale' if now-sample['received_at']>freshness else 'valid')
