"""Application lifetime owner, created once by server.main()."""
from .context import Sessions
from pathlib import Path
import os
from jarvis.memory.database import Database
from jarvis.memory.ingestion import Ingestor
from jarvis.memory.graph import Graph

class Runtime:
    def __init__(self, root, notes_dir):
        self.root, self.notes_dir = root, notes_dir
        self.sessions = Sessions()
        self.database = Database(Path(os.environ.get('JARVIS_DATA_DIR', str(Path(root)/'data'))) / 'memory.sqlite')
        self.ingestor = Ingestor(self.database)
        self.graph = Graph(self.database)
        self.index_result = self.ingestor.scan(notes_dir())

    def health(self):
        return {'ok': True, 'service': 'Jarvis', 'camera_required': False,
                'microphone_required': False, 'mode': 'local'}

    def dispatch(self, method, path, data, query):
        if method == 'GET' and path == '/api/health':
            return self.health()
        if method == 'GET' and path == '/api/memory/status':
            return {**self.database.status(), 'last_scan':self.index_result}
        if method == 'POST' and path == '/api/memory/reindex':
            self.index_result = self.ingestor.scan(self.notes_dir())
            return self.index_result
        if method == 'GET' and path == '/api/memory/document':
            return self.database.document(query.get('id', [''])[0])
        if method == 'GET' and path == '/api/graph':
            return self.graph.snapshot(query.get('focus', [None])[0])
        if method == 'POST' and path == '/api/jarvis/session':
            sid, _, state = self.sessions.get()
            return {'session_id': sid, **state.snapshot()}
        if method == 'GET' and path == '/api/jarvis/state':
            _, _, state = self.sessions.get(query.get('session_id', [''])[0])
            return state.snapshot()
        return None
