"""Explicit per-session state machine; safe public events contain no note text."""
from enum import Enum
from collections import deque
from threading import RLock
import time


class State(str, Enum):
    IDLE = 'IDLE'
    WAKE_DETECTED = 'WAKE_DETECTED'
    LISTENING = 'LISTENING'
    TRANSCRIBING = 'TRANSCRIBING'
    RETRIEVING = 'RETRIEVING'
    THINKING = 'THINKING'
    TOOL_RUNNING = 'TOOL_RUNNING'
    SPEAKING = 'SPEAKING'
    WAITING_FOR_APPROVAL = 'WAITING_FOR_APPROVAL'
    INTERRUPTED = 'INTERRUPTED'
    ERROR = 'ERROR'
    OFFLINE = 'OFFLINE'


ALLOWED = {
    'IDLE': {'WAKE_DETECTED', 'LISTENING', 'RETRIEVING', 'OFFLINE'},
    'WAKE_DETECTED': {'LISTENING', 'IDLE'},
    'LISTENING': {'TRANSCRIBING', 'IDLE'},
    'TRANSCRIBING': {'RETRIEVING', 'IDLE'},
    'RETRIEVING': {'THINKING', 'TOOL_RUNNING', 'IDLE'},
    'THINKING': {'TOOL_RUNNING', 'WAITING_FOR_APPROVAL', 'SPEAKING', 'IDLE', 'OFFLINE'},
    'TOOL_RUNNING': {'THINKING', 'SPEAKING', 'IDLE', 'WAITING_FOR_APPROVAL'},
    'WAITING_FOR_APPROVAL': {'TOOL_RUNNING', 'IDLE'},
    'SPEAKING': {'IDLE'}, 'INTERRUPTED': {'IDLE', 'RETRIEVING'},
    'ERROR': {'IDLE', 'OFFLINE', 'RETRIEVING'},
    'OFFLINE': {'IDLE', 'RETRIEVING', 'LISTENING'},
}


class StateMachine:
    def __init__(self):
        self.state = State.IDLE
        self.events = deque(maxlen=100)
        self.lock = RLock()
        self.sequence = 0

    def transition(self, target):
        target = State(target)
        with self.lock:
            if target == self.state:
                return
            if target not in (State.ERROR, State.INTERRUPTED) and target.value not in ALLOWED[self.state.value]:
                raise ValueError(f'Invalid transition: {self.state.value} -> {target.value}')
            self.state = target
            self.sequence += 1
            self.events.append({'seq': self.sequence, 'state': target.value, 'at': time.time()})

    def snapshot(self):
        with self.lock:
            return {'state': self.state.value, 'events': list(self.events)}
