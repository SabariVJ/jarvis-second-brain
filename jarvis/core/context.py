"""Bounded, expiring, per-tab context; conversation text is never persisted by default."""
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
    lock: Lock = field(default_factory=Lock)

    def select(self, doc_id):
        self.selected_id, self.selected_at = doc_id, time.monotonic()

    def selection(self):
        return self.selected_id if time.monotonic() - self.selected_at < 1800 else None

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
