"""Opt-in, bounded read-only sources for local Gmail/Calendar automations."""
from datetime import datetime, timedelta, timezone
import hashlib
import math
import threading


POLL_INTERVAL_SECONDS = 300
GMAIL_CANDIDATE_LIMIT = 50
CALENDAR_EVENT_LIMIT = 250
DEFAULT_CALENDAR_MINUTES = 60
PROVIDERS = {'GMAIL': 'IMPORTANT_EMAIL', 'CALENDAR': 'CALENDAR_APPROACHING'}


class ProviderEventSources:
    """Poll only explicitly enabled sources, on the existing scheduler thread."""

    def __init__(self, database, gmail, calendar, automations, clock=None,
                 poll_interval=POLL_INTERVAL_SECONDS):
        self.database, self.gmail, self.calendar = database, gmail, calendar
        self.automations = automations
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.poll_interval = max(POLL_INTERVAL_SECONDS, int(poll_interval))
        self._lock = threading.Lock()
        self._last_receipt_prune = 0.0
        with self.database.connect() as db:
            for provider in PROVIDERS:
                db.execute('INSERT OR IGNORE INTO provider_event_sources(provider) VALUES(?)', (provider,))

    def _now(self):
        value = self.clock()
        if not isinstance(value, datetime):
            raise ValueError('Provider source clock must return a datetime')
        if value.tzinfo is None:
            value = value.astimezone()
        return value

    def _adapter(self, provider):
        return self.gmail if provider == 'GMAIL' else self.calendar

    def status(self):
        with self.database.connect() as db:
            rows = {row['provider']: dict(row) for row in db.execute(
                'SELECT * FROM provider_event_sources')}
        sources = {}
        for provider in PROVIDERS:
            row = rows[provider]
            try:
                connected = bool(self._adapter(provider).connected)
            except Exception:
                connected = False
            enabled = bool(row['enabled'])
            state = ('DISABLED' if not enabled else
                     'NOT CONNECTED' if not connected else row['status'])
            sources[provider] = {
                'provider': provider, 'enabled': enabled, 'connected': connected,
                'status': state, 'last_poll': row['last_poll'],
                'next_poll': row['next_poll'], 'poll_interval_seconds': self.poll_interval,
                'error': row['last_error'] if state == 'ERROR' else '',
            }
        return sources

    def configure(self, provider, enabled):
        if provider not in PROVIDERS:
            raise ValueError('Provider event source is unsupported')
        if not isinstance(enabled, bool):
            raise ValueError('Provider event source enabled must be a boolean')
        now = self._now().timestamp()
        try:
            connected = bool(self._adapter(provider).connected)
        except Exception:
            connected = False
        state = ('CONFIGURED' if connected else 'NOT CONNECTED') if enabled else 'DISABLED'
        with self.database.connect() as db:
            db.execute('''UPDATE provider_event_sources SET enabled=?,status=?,last_error='',
                next_poll=? WHERE provider=?''',
                (int(enabled), state, now if enabled else None, provider))
        return self.status()[provider]

    def run_due(self):
        """Run due read-only polls; each provider failure is isolated and bounded."""
        if not self._lock.acquire(blocking=False):
            return {'polled': [], 'busy': True}
        try:
            now = self._now().timestamp()
            if now - self._last_receipt_prune >= 3600:
                self.automations.prune_provider_event_receipts(now)
                self._last_receipt_prune = now
            with self.database.connect() as db:
                rows = db.execute('''SELECT * FROM provider_event_sources
                    WHERE enabled=1 AND (next_poll IS NULL OR next_poll<=?)
                    ORDER BY provider LIMIT 2''', (now,)).fetchall()
            polled = []
            for row in rows:
                provider = row['provider']
                try:
                    connected = bool(self._adapter(provider).connected)
                    if not connected:
                        status, error = 'NOT CONNECTED', ''
                    else:
                        checked = self._poll(provider)
                        status, error = ('READY' if checked else 'CONFIGURED'), ''
                except Exception:
                    # Adapter exceptions are intentionally not copied to logs or
                    # persisted; provider payloads and transport details stay private.
                    status, error = 'ERROR', 'Provider check failed; local Jarvis remains available.'
                finished = self._now().timestamp()
                with self.database.connect() as db:
                    db.execute('''UPDATE provider_event_sources SET status=?,last_error=?,
                        last_poll=?,next_poll=? WHERE provider=? AND enabled=1''',
                        (status, error, finished, finished + self.poll_interval, provider))
                polled.append(provider)
            return {'polled': polled, 'sources': self.status()}
        finally:
            self._lock.release()

    def _enabled(self, provider):
        with self.database.connect() as db:
            row = db.execute('SELECT enabled FROM provider_event_sources WHERE provider=?', (provider,)).fetchone()
        return bool(row and row['enabled'])

    def _initialized(self, provider):
        with self.database.connect() as db:
            row = db.execute('SELECT initialized FROM provider_event_sources WHERE provider=?', (provider,)).fetchone()
        return bool(row and row['initialized'])

    def _set_initialized(self, provider):
        with self.database.connect() as db:
            db.execute('UPDATE provider_event_sources SET initialized=1 WHERE provider=?', (provider,))

    @staticmethod
    def _fingerprint(provider, event, identity):
        value = f'{provider}\0{event}\0{identity}'.encode('utf-8', 'replace')
        return hashlib.sha256(value).hexdigest()

    def _poll(self, provider):
        event = PROVIDERS[provider]
        rules = self.automations.provider_rules(provider, event)
        if not rules or not self._enabled(provider):
            return False
        if provider == 'GMAIL':
            candidates = self.gmail.automation_candidates(limit=GMAIL_CANDIDATE_LIMIT)
            if not self._enabled(provider):
                return False
            if not isinstance(candidates, list):
                raise ValueError('Gmail event source returned an invalid result')
            current_initialized = self._initialized(provider)
            if not current_initialized:
                for item in candidates[:GMAIL_CANDIDATE_LIMIT]:
                    if (isinstance(item, dict) and isinstance(item.get('id'), str)
                            and item['id'] and item.get('importance') == 'IMPORTANT'):
                        self.automations.record_provider_event_seen(
                            provider, event, self._fingerprint(provider, event, item['id']))
                self._set_initialized(provider)
                return True
            for item in candidates[:GMAIL_CANDIDATE_LIMIT]:
                if not self._enabled(provider):
                    return False
                if (not isinstance(item, dict) or not isinstance(item.get('id'), str)
                        or not item['id'] or item.get('importance') != 'IMPORTANT'):
                    continue
                context = {'importance': 'IMPORTANT'}
                self.automations.emit_provider_event(
                    provider, event, context,
                    source_reference=self._fingerprint(provider, event, item['id']),
                    automation_ids=[rule['id'] for rule in rules])
            self._set_initialized(provider)
            return True

        thresholds = {}
        for rule in rules:
            threshold = rule['conditions'].get('minutes_before', DEFAULT_CALENDAR_MINUTES)
            thresholds.setdefault(threshold, []).append(rule['id'])
        now = self._now()
        max_threshold = max(thresholds)
        result = self.calendar.events(now.isoformat(),
            (now + timedelta(minutes=max_threshold, seconds=1)).isoformat(), limit=CALENDAR_EVENT_LIMIT)
        if not self._enabled(provider):
            return False
        items = result.get('items', []) if isinstance(result, dict) else None
        if not isinstance(items, list):
            raise ValueError('Calendar event source returned an invalid result')
        current_initialized = self._initialized(provider)
        for item in items[:CALENDAR_EVENT_LIMIT]:
            if not self._enabled(provider):
                return False
            if not isinstance(item, dict) or item.get('status', 'confirmed') != 'confirmed':
                continue
            event_id, start_text = item.get('id'), item.get('start')
            if not isinstance(event_id, str) or not event_id or not isinstance(start_text, str) or not start_text:
                continue
            try:
                start = self._event_start(start_text, now.tzinfo)
            except (ValueError, OverflowError):
                continue
            seconds = (start - now).total_seconds()
            if seconds < 0 or seconds > max_threshold * 60 + 60:
                continue
            minutes_before = 0 if seconds < 60 else math.ceil(seconds / 60)
            for threshold, automation_ids in thresholds.items():
                if minutes_before > threshold:
                    continue
                identity = f'{event_id}\0{start.isoformat()}\0{threshold}'
                source_reference = self._fingerprint(provider, event, identity)
                if not current_initialized:
                    self.automations.record_provider_event_seen(provider, event, source_reference)
                elif self._enabled(provider):
                    self.automations.emit_provider_event(
                        provider, event, {'minutes_before': minutes_before},
                        source_reference=source_reference, automation_ids=automation_ids)
        self._set_initialized(provider)
        return True

    @staticmethod
    def _event_start(value, local_timezone):
        if len(value) == 10:
            start = datetime.fromisoformat(value).replace(tzinfo=local_timezone)
        else:
            start = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if start.tzinfo is None:
                start = start.replace(tzinfo=local_timezone)
        return start
