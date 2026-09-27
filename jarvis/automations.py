"""Bounded local-only automation rules with persistent, redacted audit history."""
from datetime import datetime, timedelta, timezone
import json
import re
import secrets
import threading


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
            if context.get(key) != wanted:
                return False
        return True

    def _execute(self, rule):
        action = rule['action']
        if action['type'] == 'LOCAL_NOTIFICATION':
            notification = {'automation_id': rule['id'], 'title': action['title'], 'message': action['message'],
                            'created_at': self._now().timestamp()}
        elif action['type'] == 'MORNING_BRIEFING':
            result = self.briefing.run()
            notification = {'automation_id': rule['id'], 'title': 'Morning briefing is ready',
                            'message': result.get('spoken_summary', 'Open H.O.L.O to review today’s briefing.')[:500],
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

    def _run(self, row, trigger_type, context=None):
        rule = self._record(row)
        if not rule['enabled'] or not self._matches(rule, context or {}):
            return None
        now = self._now().timestamp()
        run_status, result = 'SUCCEEDED', {}
        try:
            result = self._execute(rule)
            run_status = result.pop('status', 'SUCCEEDED')
        except Exception:
            run_status, result = 'FAILED', {'error': 'Local action failed'}
        next_run = self._next_daily(rule['trigger']['daily_at']) if trigger_type == 'TIME' and rule['trigger']['type'] == 'TIME' else None
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

    def emit_provider_event(self, provider, event, context=None):
        if provider not in PROVIDERS or event not in PROVIDER_EVENTS:
            raise ValueError('Unsupported provider event')
        if (provider, event) not in (('GMAIL', 'IMPORTANT_EMAIL'), ('CALENDAR', 'CALENDAR_APPROACHING')):
            raise ValueError('Provider event does not match its source')
        safe_context = {}
        if isinstance(context, dict):
            importance = context.get('importance')
            if importance in ('IMPORTANT', 'NORMAL'):
                safe_context['importance'] = importance
            minutes = context.get('minutes_before')
            if isinstance(minutes, int) and not isinstance(minutes, bool) and 0 <= minutes <= 1440:
                safe_context['minutes_before'] = minutes
        return self._emit('PROVIDER_EVENT', event, safe_context, provider)

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
