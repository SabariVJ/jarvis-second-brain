"""Application lifetime owner, created once by server.main()."""
from .context import Sessions
from pathlib import Path
import os
from jarvis.memory.database import Database
from jarvis.memory.ingestion import Ingestor
from jarvis.memory.graph import Graph
from jarvis.memory.embeddings import Embeddings
from jarvis.memory.retrieval import Retrieval
from jarvis.ai.astra import Astra
from .orchestrator import Orchestrator

class Runtime:
    def __init__(self, root, notes_dir):
        self.root, self.notes_dir = root, notes_dir
        self.sessions = Sessions()
        self.database = Database(Path(os.environ.get('JARVIS_DATA_DIR', str(Path(root)/'data'))) / 'memory.sqlite')
        self.ingestor = Ingestor(self.database)
        self.graph = Graph(self.database)
        self.index_result = self.ingestor.scan(notes_dir())
        self.embeddings = Embeddings(self.database)
        self.retrieval = Retrieval(self.database, self.embeddings)
        self.brain = Astra()
        self.orchestrator = Orchestrator(self.database,self.retrieval,self.graph,self.brain)

    def health(self):
        return {'ok': True, 'service': 'Jarvis', 'camera_required': False,
                'microphone_required': False, 'mode': 'configured' if self.brain.enabled else 'local',
                'model':self.brain.model, 'embeddings_enabled':self.embeddings.enabled}

    def dispatch(self, method, path, data, query):
        if method == 'GET' and path == '/api/health':
            return self.health()
        if method == 'GET' and path == '/api/memory/status':
            return {**self.database.status(), 'last_scan':self.index_result}
        if method == 'POST' and path == '/api/memory/reindex':
            self.index_result = self.ingestor.scan(self.notes_dir())
            return self.index_result
        if method == 'POST' and path == '/api/memory/embed':
            return self.embeddings.index()
        if method == 'GET' and path == '/api/memory/search':
            return self.retrieval.search(query.get('q',[''])[0])
        if method == 'GET' and path == '/api/memory/document':
            return self.database.document(query.get('id', [''])[0])
        if method == 'GET' and path == '/api/graph':
            return self.graph.snapshot(query.get('focus', [None])[0])
        if method == 'POST' and path == '/api/jarvis/session':
            sid, _, state = self.sessions.get()
            return {'session_id': sid, **state.snapshot()}
        if method == 'GET' and path == '/api/jarvis/state':
            sid = query.get('session_id', [''])[0]
            if not sid: raise ValueError('Session required')
            _, _, state = self.sessions.get(sid)
            return state.snapshot()
        if method == 'POST' and path in ('/api/jarvis/chat','/api/jarvis/context','/api/jarvis/voice-state'):
            if not data.get('session_id'): raise ValueError('Session required')
            _,context,state = self.sessions.get(data['session_id'])
            if path.endswith('/chat'):
                return self.orchestrator.chat(data.get('message'),context,state,data.get('selected_id'),bool(data.get('spoken')))
            if path.endswith('/context'):
                doc_id = data.get('document_id')
                if doc_id: self.database.document(doc_id)
                context.select(doc_id)
                return {'ok':True,'selected_id':doc_id}
            target = data.get('state')
            if target not in ('LISTENING','TRANSCRIBING','IDLE','ERROR','INTERRUPTED'):
                raise ValueError('Invalid client voice state')
            if context.lock.locked(): raise ValueError('Response is running')
            state.transition(target)
            return state.snapshot()
        return None
