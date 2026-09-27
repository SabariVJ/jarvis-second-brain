"""Bounded, expiring, per-tab context; conversation text is never persisted by default."""
from collections import deque
from dataclasses import dataclass, field
from threading import Lock, RLock
import secrets
import time

@dataclass
class Context:
    selected_id: str | None = None
    selected_at: float = 0
    touched: float = field(default_factory=time.monotonic)
    history: list = field(default_factory=list)
    research_cards: dict = field(default_factory=dict)
    last_memory_id: str | None = None
    current_context: dict | None = None
    context_events: deque = field(default_factory=lambda: deque(maxlen=32))
    lock: Lock = field(default_factory=Lock)

    def select(self, doc_id):
        self.selected_id, self.selected_at = doc_id, time.monotonic()

    def selection(self):
        return self.selected_id if time.monotonic() - self.selected_at < 1800 else None

    def record_context(self, event, object_type, object_id, source_reference='', metadata=None):
        """Record a short-lived interaction reference; never persist user content."""
        now = time.time()
        safe_metadata = {}
        for key in ('title', 'kind', 'label', 'status'):
            value = (metadata or {}).get(key)
            if isinstance(value, str):
                safe_metadata[key] = value.replace('\x00', '')[:240]
        count = (metadata or {}).get('count')
        if isinstance(count, int) and 0 <= count <= 10000:
            safe_metadata['count'] = count
        item = {
            'event': event, 'object_type': object_type, 'object_id': object_id,
            'source_reference': str(source_reference or '')[:500], 'timestamp': now,
            'metadata': safe_metadata,
        }
        self.current_context = item
        self.context_events.append(item)
        if object_type == 'NOTE' and event in ('NOTE_SELECTED', 'NOTE_OPENED'):
            self.select(object_id)
        return item

    def context_snapshot(self):
        current = self.current_context
        if current and time.time() - current['timestamp'] >= 1800:
            self.current_context = None
            current = None
        return {'current_context': dict(current) if current else None,
                'context_events': list(self.context_events)}

class Sessions:
    def __init__(self):
        self.items = {}
        self.lock = RLock()

    def get(self, session_id=None):
        from .state import StateMachine
        with self.lock:
            now = time.monotonic()
            self.items = {k: v for k, v in self.items.items() if now - v[0].touched < 3600 or v[0].lock.locked()}
            if session_id:
                if session_id not in self.items:
                    raise ValueError('Session expired; reload Jarvis')
            else:
                if len(self.items) >= 64:
                    raise ValueError('Too many sessions')
                session_id = secrets.token_urlsafe(24)
                self.items[session_id] = (Context(), StateMachine())
            context, machine = self.items[session_id]
            context.touched = now
            return session_id, context, machine
