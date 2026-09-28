"""Bounded local-only automation rules with persistent, redacted audit history."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
import secrets
import threading
from jarvis.security import contains_secret


EVENTS = {'BUILD_FINISHED', 'DEADLINE_REACHED', 'FOCUS_STARTED', 'FOCUS_ENDED'}
STATES = {'FOCUS_ACTIVE', 'FOCUS_PAUSED'}
PROVIDER_EVENTS = {'IMPORTANT_EMAIL', 'CALENDAR_APPROACHING'}
ACTION_TYPES = {'LOCAL_NOTIFICATION', 'MORNING_BRIEFING', 'DISTRACTION_MONITOR'}
PROVIDERS = {'GMAIL', 'CALENDAR'}


def _text(value, label, maximum):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError(f'{label} must contain 1–{maximum} characters')
    if any(ord(char) < 32 and char not in '\n\t' for char in value):
        raise ValueError(f'{label} contains unsupported control characters')
    if contains_secret(value):
        raise ValueError(f'{label} cannot contain credentials or secrets')
    return value.strip()


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def validate_rule(data):
    if not isinstance(data, dict):
        raise ValueError('Automation must be an object')
    allowed = {'name', 'trigger', 'conditions', 'action', 'enabled'}
    if set(data) - allowed:
        raise ValueError('Automation contains unsupported fields')
    name = _text(data.get('name'), 'Name', 80)
    trigger = data.get('trigger')
    if not isinstance(trigger, dict) or trigger.get('type') not in ('TIME', 'EVENT', 'STATE', 'PROVIDER_EVENT'):
        raise ValueError('Choose a supported TIME, EVENT, STATE or PROVIDER_EVENT trigger')
    kind = trigger['type']
    if kind == 'TIME':
        if set(trigger) != {'type', 'daily_at'} or not isinstance(trigger['daily_at'], str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', trigger['daily_at']):
            raise ValueError('TIME trigger requires daily_at in 24-hour HH:MM format')
        clean_trigger = {'type': kind, 'daily_at': trigger['daily_at']}
    elif kind == 'EVENT':
        if set(trigger) != {'type', 'event'} or trigger['event'] not in EVENTS:
            raise ValueError('EVENT trigger is not supported')
        clean_trigger = {'type': kind, 'event': trigger['event']}
    elif kind == 'STATE':
        if set(trigger) != {'type', 'state'} or trigger['state'] not in STATES:
            raise ValueError('STATE trigger is not supported')
        clean_trigger = {'type': kind, 'state': trigger['state']}
    else:
        if set(trigger) != {'type', 'provider', 'event'} or trigger['provider'] not in PROVIDERS or trigger['event'] not in PROVIDER_EVENTS:
            raise ValueError('PROVIDER_EVENT trigger is not supported')
        if (trigger['provider'], trigger['event']) not in (('GMAIL', 'IMPORTANT_EMAIL'), ('CALENDAR', 'CALENDAR_APPROACHING')):
            raise ValueError('That event is not available from this provider')
        clean_trigger = {'type': kind, 'provider': trigger['provider'], 'event': trigger['event']}

    conditions = data.get('conditions', {})
    if not isinstance(conditions, dict) or set(conditions) - {'importance', 'minutes_before'}:
        raise ValueError('Conditions contain unsupported fields')
    clean_conditions = {}
    if 'importance' in conditions:
        if conditions['importance'] not in ('IMPORTANT', 'NORMAL'):
            raise ValueError('Importance condition must be IMPORTANT or NORMAL')
        clean_conditions['importance'] = conditions['importance']
    if 'minutes_before' in conditions:
        value = conditions['minutes_before']
        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 1440:
            raise ValueError('minutes_before must be between 0 and 1440')
        clean_conditions['minutes_before'] = value

    action = data.get('action')
    if not isinstance(action, dict) or action.get('type') not in ACTION_TYPES:
        raise ValueError('Choose a supported local action')
    action_type = action['type']
    if action_type == 'LOCAL_NOTIFICATION':
        if set(action) != {'type', 'title', 'message'}:
            raise ValueError('LOCAL_NOTIFICATION requires a title and message')
        clean_action = {'type': action_type, 'title': _text(action['title'], 'Notification title', 100),
                        'message': _text(action['message'], 'Notification message', 500)}
    elif set(action) != {'type'}:
        raise ValueError(f'{action_type} does not accept action arguments')
    else:
        clean_action = {'type': action_type}
    enabled = data.get('enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('enabled must be a boolean')
    return {'name': name, 'trigger': clean_trigger, 'conditions': clean_conditions,
            'action': clean_action, 'enabled': enabled}


class AutomationEngine:
    """Rules only dispatch to local display/briefing/focus callbacks; no external writes."""
    def __init__(self, database, briefing, focus, clock=None):
        self.database, self.briefing, self.focus = database, briefing, focus
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._notifications = []
        self._due_lock = threading.Lock()

    def _now(self):
        value = self.clock()
        if value.tzinfo is None:
            value = value.astimezone()
        return value

    def _next_daily(self, daily_at, after=None):
        current = (after or self._now()).astimezone()
        hour, minute = map(int, daily_at.split(':'))
        candidate = current.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= current:
            candidate += timedelta(days=1)
        return candidate.astimezone(timezone.utc).timestamp()

    def _record(self, row):
        return {'id': row['id'], 'name': row['name'], 'trigger': json.loads(row['trigger_json']),
                'conditions': json.loads(row['conditions_json']), 'action': json.loads(row['action_json']),
                'enabled': bool(row['enabled']), 'created_at': row['created_at'], 'last_run': row['last_run'],
                'next_run': row['next_run'], 'permission_requirement': row['permission_requirement'],
                'status': row['status']}

    def list(self):
        with self.database.connect() as db:
            items = [self._record(row) for row in db.execute('SELECT * FROM automations ORDER BY created_at DESC LIMIT 200')]
            runs = [dict(row) for row in db.execute('SELECT id,automation_id,started_at,finished_at,trigger_type,status,result_json FROM automation_runs ORDER BY id DESC LIMIT 100')]
        for run in runs:
            run['result'] = json.loads(run.pop('result_json'))
        return {'items': items, 'runs': runs, 'notifications': self._notifications[-20:],
                'supported': {'triggers': ['TIME', 'EVENT', 'STATE', 'PROVIDER_EVENT'],
                              'events': sorted(EVENTS), 'states': sorted(STATES),
                              'provider_events': sorted(PROVIDER_EVENTS), 'actions': sorted(ACTION_TYPES)}}

    def create(self, data):
        rule = validate_rule(data)
        now = self._now().timestamp()
        next_run = self._next_daily(rule['trigger']['daily_at'], self._now()) if rule['enabled'] and rule['trigger']['type'] == 'TIME' else None
        rule_id = 'auto_' + secrets.token_hex(12)
        with self.database.connect() as db:
            if db.execute('SELECT COUNT(*) FROM automations').fetchone()[0] >= 100:
                raise ValueError('The local automation limit is 100 rules')
            db.execute('''INSERT INTO automations(id,name,trigger_json,conditions_json,action_json,enabled,created_at,
                next_run,permission_requirement,status) VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (rule_id, rule['name'], _json(rule['trigger']), _json(rule['conditions']), _json(rule['action']),
                 int(rule['enabled']), now, next_run, 'L0_READ_LOCAL_ONLY', 'READY' if rule['enabled'] else 'DISABLED'))
        return self.get(rule_id)

    def get(self, rule_id):
        with self.database.connect() as db:
            row = db.execute('SELECT * FROM automations WHERE id=?', (rule_id,)).fetchone()
        if not row:
            raise ValueError('Automation not found')
        return self._record(row)

    def update(self, rule_id, data):
        rule = validate_rule(data)
        with self.database.connect() as db:
            current = db.execute('SELECT created_at FROM automations WHERE id=?', (rule_id,)).fetchone()
            if not current:
                raise ValueError('Automation not found')
            next_run = self._next_daily(rule['trigger']['daily_at']) if rule['enabled'] and rule['trigger']['type'] == 'TIME' else None
            db.execute('''UPDATE automations SET name=?,trigger_json=?,conditions_json=?,action_json=?,enabled=?,
                next_run=?,permission_requirement='L0_READ_LOCAL_ONLY',status=? WHERE id=?''',
                (rule['name'], _json(rule['trigger']), _json(rule['conditions']), _json(rule['action']),
                 int(rule['enabled']), next_run, 'READY' if rule['enabled'] else 'DISABLED', rule_id))
        return self.get(rule_id)

    def set_enabled(self, rule_id, enabled):
        if not isinstance(enabled, bool):
            raise ValueError('enabled must be a boolean')
        rule = self.get(rule_id)
        next_run = self._next_daily(rule['trigger']['daily_at']) if enabled and rule['trigger']['type'] == 'TIME' else None
        with self.database.connect() as db:
            result = db.execute('UPDATE automations SET enabled=?,status=?,next_run=? WHERE id=?',
                (int(enabled), 'READY' if enabled else 'DISABLED', next_run, rule_id))
            if result.rowcount != 1:
                raise ValueError('Automation not found')
        return self.get(rule_id)

    def delete(self, rule_id):
        with self.database.connect() as db:
            result = db.execute('DELETE FROM automations WHERE id=?', (rule_id,))
        if not result.rowcount:
            raise ValueError('Automation not found')
        return {'ok': True, 'id': rule_id}

    def _matches(self, rule, context):
        for key, wanted in rule['conditions'].items():
            if (rule['trigger'].get('provider') == 'CALENDAR' and key == 'minutes_before'):
                actual = context.get(key)
                if not isinstance(actual, int) or isinstance(actual, bool) or actual < 0 or actual > wanted:
                    return False
                continue
            if context.get(key) != wanted:
                return False
        return True

    def _execute(self, rule, provenance=None):
        action = rule['action']
        if action['type'] == 'LOCAL_NOTIFICATION':
            notification = {'automation_id': rule['id'], 'title': action['title'], 'message': action['message'],
                            'created_at': self._now().timestamp()}
            if provenance:
                notification['source'] = provenance
        elif action['type'] == 'MORNING_BRIEFING':
            result = self.briefing.run()
            notification = {'automation_id': rule['id'], 'title': 'Morning briefing is ready',
                            'message': result.get('spoken', 'Open H.O.L.O to review today’s briefing.')[:500],
                            'created_at': self._now().timestamp()}
        else:
            state = self.focus.status()
            if state.get('state') != 'ACTIVE':
                return {'status': 'SKIPPED', 'reason': 'Focus session is not active'}
            notification = {'automation_id': rule['id'], 'title': 'Focus monitoring active',
                            'message': 'Local focus monitoring remains active.', 'created_at': self._now().timestamp()}
        self._notifications.append(notification)
        self._notifications = self._notifications[-20:]
        return {'status': 'SUCCEEDED', 'notification_created': True}

    def _run(self, row, trigger_type, context=None, provenance=None):
        rule = self._record(row)
        if not rule['enabled'] or not self._matches(rule, context or {}):
            return None
        now = self._now().timestamp()
        run_status, result = 'SUCCEEDED', {}
        try:
            result = self._execute(rule, provenance)
            run_status = result.pop('status', 'SUCCEEDED')
        except Exception:
            run_status, result = 'FAILED', {'error': 'Local action failed'}
        next_run = self._next_daily(rule['trigger']['daily_at']) if trigger_type == 'TIME' and rule['trigger']['type'] == 'TIME' else None
        if provenance:
            result['source'] = provenance
        with self.database.connect() as db:
            db.execute('UPDATE automations SET last_run=?,next_run=? WHERE id=?', (now, next_run, rule['id']))
            db.execute('''INSERT INTO automation_runs(automation_id,started_at,finished_at,trigger_type,status,result_json)
                VALUES(?,?,?,?,?,?)''', (rule['id'], now, self._now().timestamp(), trigger_type, run_status, _json(result)))
            db.execute('DELETE FROM automation_runs WHERE id NOT IN (SELECT id FROM automation_runs ORDER BY id DESC LIMIT 1000)')
        return {'automation_id': rule['id'], 'status': run_status, **result}

    def run_due(self):
        with self._due_lock:
            now = self._now().timestamp()
            with self.database.connect() as db:
                rows = db.execute("SELECT * FROM automations WHERE enabled=1 AND next_run IS NOT NULL AND next_run<=? ORDER BY next_run LIMIT 100", (now,)).fetchall()
            return {'runs': [result for row in rows if (result := self._run(row, 'TIME')) is not None]}

    def emit_event(self, event, context=None):
        if event not in EVENTS:
            raise ValueError('Unsupported local event')
        return self._emit('EVENT', event, context or {})

    def emit_state(self, state, context=None):
        if state not in STATES:
            raise ValueError('Unsupported local state')
        return self._emit('STATE', state, context or {})

    def provider_rules(self, provider, event):
        if provider not in PROVIDERS or (provider, event) not in (
                ('GMAIL', 'IMPORTANT_EMAIL'), ('CALENDAR', 'CALENDAR_APPROACHING')):
            raise ValueError('Unsupported provider event')
        with self.database.connect() as db:
            rows = db.execute("SELECT * FROM automations WHERE enabled=1 ORDER BY created_at LIMIT 200").fetchall()
        return [self._record(row) for row in rows
                if (trigger := json.loads(row['trigger_json'])).get('type') == 'PROVIDER_EVENT'
                and trigger.get('provider') == provider and trigger.get('event') == event]

    def _provider_source_key(self, provider, event, source_reference):
        if (provider, event) not in (('GMAIL', 'IMPORTANT_EMAIL'), ('CALENDAR', 'CALENDAR_APPROACHING')):
            raise ValueError('Provider event does not match its source')
        if (not isinstance(source_reference, str) or not source_reference or len(source_reference) > 500
                or any(ord(char) < 32 for char in source_reference) or contains_secret(source_reference)):
            raise ValueError('Provider event source reference is invalid')
        return hashlib.sha256(f'{provider}\0{event}\0{source_reference}'.encode('utf-8')).hexdigest()

    def record_provider_event_seen(self, provider, event, source_reference):
        """Persist a content-free baseline/dedupe receipt without firing rules."""
        source_key = self._provider_source_key(provider, event, source_reference)
        now = self._now().timestamp()
        with self.database.connect() as db:
            db.execute('''INSERT OR IGNORE INTO provider_event_receipts
                (provider,event,source_key,automation_id,seen_at) VALUES(?,?,?,?,?)''',
                (provider, event, source_key, '*', now))
            self._prune_provider_receipts(db, now)
        return source_key

    @staticmethod
    def _prune_provider_receipts(db, now):
        db.execute('DELETE FROM provider_event_receipts WHERE seen_at<?', (now - 90 * 86400,))
        db.execute('''DELETE FROM provider_event_receipts WHERE rowid NOT IN
            (SELECT rowid FROM provider_event_receipts ORDER BY seen_at DESC LIMIT 5000)''')

    def prune_provider_event_receipts(self, now=None):
        current = self._now().timestamp() if now is None else float(now)
        with self.database.connect() as db:
            self._prune_provider_receipts(db, current)

    def emit_provider_event(self, provider, event, context=None, source_reference=None, automation_ids=None):
        if provider not in PROVIDERS or event not in PROVIDER_EVENTS:
            raise ValueError('Unsupported provider event')
        if (provider, event) not in (('GMAIL', 'IMPORTANT_EMAIL'), ('CALENDAR', 'CALENDAR_APPROACHING')):
            raise ValueError('Provider event does not match its source')
        if automation_ids is not None and (not isinstance(automation_ids, (list, tuple))
                or len(automation_ids) > 200 or any(not isinstance(value, str) or not re.fullmatch(r'auto_[0-9a-f]{24}', value)
                                                       for value in automation_ids)):
            raise ValueError('Provider event rule selection is invalid')
        safe_context = {}
        if isinstance(context, dict):
            importance = context.get('importance')
            if importance in ('IMPORTANT', 'NORMAL'):
                safe_context['importance'] = importance
            minutes = context.get('minutes_before')
            if isinstance(minutes, int) and not isinstance(minutes, bool) and 0 <= minutes <= 1440:
                safe_context['minutes_before'] = minutes
        if source_reference is None:
            return self._emit('PROVIDER_EVENT', event, safe_context, provider)

        source_key = self._provider_source_key(provider, event, source_reference)
        provenance = {'provider': provider, 'event': event, 'source_id': source_key}
        now = self._now().timestamp()
        with self.database.connect() as db:
            if db.execute('''SELECT 1 FROM provider_event_receipts
                    WHERE provider=? AND event=? AND source_key=? AND automation_id='*' ''',
                    (provider, event, source_key)).fetchone():
                return {'runs': [], 'duplicate': True}
            rows = db.execute("SELECT * FROM automations WHERE enabled=1 ORDER BY created_at LIMIT 200").fetchall()
            claimed = []
            selected = set(automation_ids) if automation_ids is not None else None
            for row in rows:
                trigger = json.loads(row['trigger_json'])
                if (trigger.get('type') != 'PROVIDER_EVENT' or trigger.get('provider') != provider
                        or trigger.get('event') != event or (selected is not None and row['id'] not in selected)):
                    continue
                inserted = db.execute('''INSERT OR IGNORE INTO provider_event_receipts
                    (provider,event,source_key,automation_id,seen_at) VALUES(?,?,?,?,?)''',
                    (provider, event, source_key, row['id'], now))
                if inserted.rowcount:
                    claimed.append(row)
            db.execute('''INSERT OR IGNORE INTO provider_event_receipts
                (provider,event,source_key,automation_id,seen_at) VALUES(?,?,?,?,?)''',
                (provider, event, source_key, '*', now))
            self._prune_provider_receipts(db, now)
        return {'runs': [result for row in claimed
                         if (result := self._run(row, 'PROVIDER_EVENT', safe_context, provenance)) is not None]}

    def _emit(self, kind, name, context, provider=None):
        with self.database.connect() as db:
            rows = db.execute('SELECT * FROM automations WHERE enabled=1 ORDER BY created_at LIMIT 200').fetchall()
        results = []
        for row in rows:
            rule = self._record(row)
            trigger = rule['trigger']
            if trigger['type'] != kind:
                continue
            matches = trigger.get('event', trigger.get('state')) == name
            if provider:
                matches = matches and trigger.get('provider') == provider
            if matches and (result := self._run(row, kind, context)) is not None:
                results.append(result)
        return {'runs': results}
