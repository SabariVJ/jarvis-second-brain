"""Application lifetime owner, created once by server.main()."""
from .context import Sessions

class Runtime:
    def __init__(self, root, notes_dir):
        self.root, self.notes_dir = root, notes_dir
        self.sessions = Sessions()

    def health(self):
        return {'ok': True, 'service': 'Jarvis', 'camera_required': False,
                'microphone_required': False, 'mode': 'local'}

    def dispatch(self, method, path, data, query):
        if method == 'GET' and path == '/api/health':
            return self.health()
        if method == 'POST' and path == '/api/jarvis/session':
            sid, _, state = self.sessions.get()
            return {'session_id': sid, **state.snapshot()}
        if method == 'GET' and path == '/api/jarvis/state':
            _, _, state = self.sessions.get(query.get('session_id', [''])[0])
            return state.snapshot()
        return None
