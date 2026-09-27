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
from jarvis.research import WebResearch
from jarvis.ai.vision import Vision
from jarvis.focus import FocusLock
from jarvis.integrations.gmail import GmailAdapter
from jarvis.integrations.calendar import CalendarAdapter
from jarvis.briefing import MorningBriefing
from jarvis.memory.long_term import LongTermMemory
from jarvis.integrations.telegram import TelegramAdapter
from .context import Context
from .state import StateMachine
from io import BytesIO
from jarvis.documents import DocumentAutomation

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
        self.research = WebResearch(model=self.brain.model)
        self.vision = Vision(model=self.brain.model)
        self.focus = FocusLock(Path(os.environ.get('JARVIS_DATA_DIR', str(Path(root)/'data'))) / 'focus.json')
        self.gmail = GmailAdapter()
        self.calendar = CalendarAdapter()
        self.briefing = MorningBriefing(self.database,self.gmail,self.calendar,self.focus)
        self.long_term_memory=LongTermMemory(self.database)
        data_dir=Path(os.environ.get('JARVIS_DATA_DIR', str(Path(root)/'data')))
        self.documents=DocumentAutomation(self.database,data_dir)
        self.orchestrator = Orchestrator(self.database,self.retrieval,self.graph,self.brain,self.research,self.long_term_memory,self.documents)
        self._telegram_sessions={}
        transcriber=None
        if self.brain.enabled:
            transcriber=self._transcribe_telegram_voice
        self.telegram=TelegramAdapter(on_text=self._telegram_chat,transcriber=transcriber,artifact_provider=self.documents.telegram_artifact)

    def health(self):
        return {'ok': True, 'service': 'Jarvis', 'camera_required': False,
                'microphone_required': False, 'mode': 'configured' if self.brain.enabled else 'local',
                'model':self.brain.model, 'embeddings_enabled':self.embeddings.enabled}

    def _record_context(self, context, data):
        events = {
            'NOTE_SELECTED':'NOTE','NOTE_OPENED':'NOTE','NOTE_MOVED':'NOTE','NOTE_CRUSHED':'NOTE',
            'NODE_SELECTED':'NODE','NODE_EXPANDED':'NODE','NODE_COLLAPSED':'NODE',
            'CARD_SELECTED':{'DOCUMENT','RESEARCH','MEMORY','EMAIL','CALENDAR','INVOICE','FOCUS','TELEGRAM','SYSTEM','APPROVAL'},
            'CARD_OPENED':{'DOCUMENT','RESEARCH','MEMORY','EMAIL','CALENDAR','INVOICE','FOCUS','TELEGRAM','SYSTEM','APPROVAL'},
            'RESEARCH_SELECTED':'RESEARCH','EMAIL_SELECTED':'EMAIL','CALENDAR_SELECTED':'CALENDAR',
            'INVOICE_SELECTED':'INVOICE','MEMORY_SELECTED':'MEMORY','FOCUS_SELECTED':'FOCUS',
            'GRAPH_FOCUSED':'GRAPH',
        }
        event=data.get('event')
        if event is None and 'document_id' in data:  # Phase 0–21 API compatibility.
            event='NOTE_SELECTED';data={**data,'object_type':'NOTE','object_id':data.get('document_id')}
        if event not in events:raise ValueError('Unsupported H.O.L.O context event')
        object_type=data.get('object_type');allowed=events[event]
        if object_type not in (allowed if isinstance(allowed,set) else {allowed}):raise ValueError('Context event and object type do not match')
        object_id=data.get('object_id')
        if event=='GRAPH_FOCUSED' and object_id is None:object_id='graph'
        if not isinstance(object_id,str) or not object_id or len(object_id)>160 or any(ord(c)<32 for c in object_id):
            raise ValueError('Context object ID is invalid')
        metadata=data.get('metadata',{})
        if not isinstance(metadata,dict) or len(metadata)>8:raise ValueError('Context metadata must be a small object')
        source_reference=''
        if object_type=='NOTE':
            note=self.database.document(object_id)
            source_reference=note.get('relative_path','')
            metadata={'title':note.get('title',''), 'kind':'NOTE'}
        elif object_type=='NODE':
            node=next((n for n in self.graph.snapshot()['nodes'] if n['id']==object_id),None)
            if not node:raise ValueError('Graph node is unavailable')
            metadata={'title':node.get('label',''),'kind':node.get('kind','')}
            source_reference=node.get('path','')
        elif object_type in ('DOCUMENT','INVOICE'):
            card=self.documents._card(object_id)
            if card.get('status')!='active':raise ValueError('Generated document is unavailable')
            if object_type=='INVOICE' and card.get('kind')!='invoice':raise ValueError('Selected item is not an invoice')
            if object_type=='DOCUMENT' and card.get('kind')=='invoice':raise ValueError('Select this item as an invoice')
            metadata={'title':card.get('title',''),'kind':card.get('kind','')}
            source_reference=object_id
        elif object_type=='RESEARCH':
            card=context.research_cards.get(object_id)
            if not card:raise ValueError('Research card is unavailable or expired')
            metadata={'title':card.get('title',''),'kind':'RESEARCH'}
        elif object_type=='MEMORY':
            memory=self.long_term_memory.inspect(object_id)
            metadata={'title':memory.get('category',''),'kind':'PERSONAL MEMORY'}
            source_reference=memory.get('source_reference','')
        elif object_type=='FOCUS':
            focus=self.focus.status()
            if object_id!='active' or focus.get('state') not in ('ACTIVE','PAUSED'):
                raise ValueError('There is no active focus session')
            metadata={'title':focus.get('goal',''),'kind':'FOCUS','status':focus.get('state','')}
        else:
            # Provider identifiers and labels are display context only. They are
            # bounded and never confer permission to execute an action.
            source_reference=data.get('source_reference','')
        item=context.record_context(event,object_type,object_id,source_reference,metadata)
        return {'ok':True,'selected_id':context.selection(),'current_context':item}

    def dispatch(self, method, path, data, query):
        if method == 'GET' and path == '/api/health':
            return {**self.health(),'screen_vision_enabled':self.vision.enabled}
        if method == 'GET' and path == '/api/focus':
            return self.focus.status()
        if method == 'GET' and path == '/api/integrations/gmail': return self.gmail.status()
        if method == 'GET' and path == '/api/integrations/calendar': return self.calendar.status()
        if method == 'GET' and path == '/api/integrations/telegram': return self.telegram.status()
        if method == 'POST' and path == '/api/telegram/start': return self.telegram.start()
        if method == 'POST' and path == '/api/telegram/stop': return self.telegram.stop()
        if method == 'GET' and path == '/api/documents': return self.documents.list_documents()
        if method == 'POST' and path == '/api/documents/invoice/prepare': return self.documents.prepare_invoice(data)
        if method == 'POST' and path == '/api/documents/invoice/create': return self.documents.create_invoice(data)
        if method == 'POST' and path == '/api/documents/create':
            return self.documents.create_document(data.get('kind'),data.get('title'),data.get('content'),data.get('source_ids'))
        if method == 'POST' and path == '/api/documents/action':
            return self.documents.action(data.get('id'),data.get('action'),data.get('confirmation'))
        if method == 'POST' and path == '/api/briefing/morning': return self.briefing.run()
        if method == 'GET' and path == '/api/personal-memory':
            memory_id=query.get('id',[''])[0]
            if memory_id:return self.long_term_memory.inspect(memory_id)
            return {'items':self.long_term_memory.search(query.get('q',[''])[0],query.get('category',[None])[0])}
        if method == 'POST' and path == '/api/personal-memory/remember':
            return self.long_term_memory.capture_allowed(data.get('content'),data.get('source_type','user_explicit'))
        if method == 'POST' and path == '/api/personal-memory/update':
            return self.long_term_memory.update(data.get('id'),data.get('content'),data.get('category'))
        if method == 'POST' and path == '/api/personal-memory/forget':
            return self.long_term_memory.forget(data.get('id'))
        if method == 'POST' and path == '/api/gmail/list':
            return self.gmail.list_messages(data.get('mode','inbox'),data.get('query',''),data.get('limit',20))
        if method == 'POST' and path == '/api/gmail/thread': return self.gmail.thread(data.get('thread_id'))
        if method == 'POST' and path == '/api/gmail/summarize': return self.gmail.summarize(data.get('thread_id'))
        if method == 'POST' and path == '/api/gmail/draft':
            return self.gmail.create_draft(data.get('to'),data.get('subject'),data.get('body'))
        if method == 'POST' and path == '/api/gmail/reply-draft':
            return self.gmail.reply_draft(data.get('thread_id'),data.get('body'))
        if method == 'POST' and path == '/api/gmail/send':
            return self.gmail.send_draft(data.get('draft_id'),data.get('confirmation'))
        if method == 'POST' and path == '/api/calendar/today': return self.calendar.today()
        if method == 'POST' and path == '/api/calendar/tomorrow': return self.calendar.tomorrow()
        if method == 'POST' and path == '/api/calendar/events':
            return self.calendar.events(data.get('start'),data.get('end'),data.get('query',''),data.get('limit',100))
        if method == 'POST' and path == '/api/calendar/range':
            return self.calendar.events(data.get('start'),data.get('end'),data.get('query',''),data.get('limit',100))
        if method == 'POST' and path == '/api/calendar/search':
            return self.calendar.events(data.get('start'),data.get('end'),data.get('query',''),data.get('limit',100))
        if method == 'POST' and path == '/api/calendar/availability':
            return self.calendar.availability(data.get('start'),data.get('end'))
        if method == 'POST' and path == '/api/calendar/create':
            return self.calendar.create(data.get('summary'),data.get('start'),data.get('end'),data.get('confirmation'),data.get('description',''))
        if method == 'POST' and path == '/api/calendar/reschedule':
            return self.calendar.reschedule(data.get('event_id'),data.get('start'),data.get('end'),data.get('confirmation'))
        if method == 'POST' and path == '/api/calendar/cancel':
            return self.calendar.cancel(data.get('event_id'),data.get('confirmation'))
        if method == 'POST' and path == '/api/focus/start':
            return self.focus.start(data.get('minutes',90),data.get('goal','Focus session'),data.get('allowed_apps'),data.get('distractions'))
        if method == 'POST' and path == '/api/focus/pause': return self.focus.pause()
        if method == 'POST' and path == '/api/focus/resume': return self.focus.resume()
        if method == 'POST' and path == '/api/focus/stop': return self.focus.stop()
        if method == 'POST' and path in ('/api/vision/screen','/api/vision/camera'):
            return self.vision.analyze_frame(data.get('question'),data.get('image_data_url'))
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
            _, context, state = self.sessions.get(sid)
            return {**state.snapshot(),**context.context_snapshot()}
        if method == 'GET' and path == '/api/research/cards':
            sid = query.get('session_id',[''])[0]
            if not sid: raise ValueError('Session required')
            _,context,_ = self.sessions.get(sid)
            return {'cards':list(context.research_cards.values())}
        if method == 'POST' and path == '/api/research/card':
            if not data.get('session_id'): raise ValueError('Session required')
            _,context,_ = self.sessions.get(data['session_id'])
            action,card_id = data.get('action'),data.get('card_id')
            if action not in ('keep','dismiss','save') or not isinstance(card_id,str):
                raise ValueError('Invalid research card action')
            if not context.lock.acquire(False): raise ValueError('Wait for current response')
            try:
                card = context.research_cards.get(card_id)
                if not card: raise ValueError('Research card unavailable or expired')
                if action == 'dismiss':
                    del context.research_cards[card_id]
                    return {'ok':True,'action':action,'card_id':card_id}
                if action == 'keep':
                    card['status']='pinned'
                    return {'ok':True,'action':action,'card':card}
                doc_id = self.ingestor.save_research(card)
                card['status']='saved';card['document_id']=doc_id
                return {'ok':True,'action':action,'card':card,'document_id':doc_id}
            finally:
                context.lock.release()
        if method == 'POST' and path in ('/api/jarvis/chat','/api/jarvis/context','/api/jarvis/voice-state'):
            if not data.get('session_id'): raise ValueError('Session required')
            _,context,state = self.sessions.get(data['session_id'])
            if path.endswith('/chat'):
                return self.orchestrator.chat(data.get('message'),context,state,data.get('selected_id'),bool(data.get('spoken')))
            if path.endswith('/context'):
                if context.lock.locked(): raise ValueError('Wait for the current response before selecting another source')
                if data.get('event')=='CONTEXT_CLEAR':
                    context.current_context=None;context.select(None)
                    return {'ok':True,'selected_id':None,'current_context':None}
                return self._record_context(context,data)
            target = data.get('state')
            if target not in ('WAKE_DETECTED','LISTENING','TRANSCRIBING','SPEAKING','IDLE','ERROR','INTERRUPTED'):
                raise ValueError('Invalid client voice state')
            if context.lock.locked(): raise ValueError('Response is running')
            state.transition(target)
            return state.snapshot()
        return None

    def _telegram_chat(self,sender_id,message):
        if sender_id not in self.telegram.allowed_user_ids:raise ValueError('Sender is not allowlisted')
        session=self._telegram_sessions.get(sender_id)
        if session is None:
            session=(Context(),StateMachine());self._telegram_sessions[sender_id]=session
        context,state=session
        return self.orchestrator.chat(message,context,state,capture_memories=False,origin='telegram')

    def _transcribe_telegram_voice(self,audio,filename):
        if not self.brain.enabled:raise ValueError('Voice transcription is not connected')
        response=self.brain.client.audio.transcriptions.create(model=os.environ.get('JARVIS_TELEGRAM_TRANSCRIBE_MODEL','gpt-4o-mini-transcribe'),
            file=(filename,BytesIO(audio),'audio/ogg'))
        return getattr(response,'text','')
