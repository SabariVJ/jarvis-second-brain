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
from jarvis.tools import Tool
from jarvis.approvals import ApprovalEngine
from jarvis.cards import VisualCards
from jarvis.windows import WindowsTools
from jarvis.automations import AutomationEngine
from jarvis.provider_events import ProviderEventSources

class Runtime:
    def __init__(self, root, notes_dir):
        self.root, self.notes_dir = root, notes_dir
        self.sessions = Sessions()
        self.database = Database(Path(os.environ.get('JARVIS_DATA_DIR', str(Path(root)/'data'))) / 'memory.sqlite')
        self.cards=VisualCards(self.database)
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
        self.automations = AutomationEngine(self.database,self.briefing,self.focus)
        self.provider_events = ProviderEventSources(self.database,self.gmail,self.calendar,self.automations)
        self.long_term_memory=LongTermMemory(self.database)
        data_dir=Path(os.environ.get('JARVIS_DATA_DIR', str(Path(root)/'data')))
        self.documents=DocumentAutomation(self.database,data_dir)
        self.windows=WindowsTools([notes_dir(),self.documents.generated_dir])
        self.orchestrator = Orchestrator(self.database,self.retrieval,self.graph,self.brain,self.research,self.long_term_memory,self.documents)
        self._telegram_sessions={}
        transcriber=None
        if self.brain.enabled:
            transcriber=self._transcribe_telegram_voice
        self.telegram=TelegramAdapter(on_text=self._telegram_chat,transcriber=transcriber,artifact_provider=self.documents.telegram_artifact)
        self._register_tool_catalog()
        self.approvals=ApprovalEngine(self.database,self.orchestrator.tools)
        self.orchestrator.approvals=self.approvals

    def _register_tool_catalog(self):
        registry=self.orchestrator.tools
        def s(maximum=4000,minimum=1,**extra):return {'type':'string','minLength':minimum,'maxLength':maximum,**extra}
        def obj(properties,required=None):return {'type':'object','properties':properties,'required':list(required if required is not None else properties)}
        def add(name,description,arguments,permission,function,available=True,verifier=None):
            if name not in registry.tools:
                registry.register(Tool(name,arguments=arguments,description=description,
                    permission_class=permission,function=function,available=available,verifier=verifier))
        off=lambda *args,**kwargs:None
        active_focus={'minutes':{'type':'integer','minimum':1,'maximum':480},'goal':s(120),
            'allowed_apps':{'type':'array','items':s(80),'maxItems':30,'required':False},
            'distractions':{'type':'array','items':s(120),'maxItems':30,'required':False}}
        add('remember','Save a personal fact from an explicit user request.',
            {'content':s(2000),'source_type':{'type':'string','enum':['user_explicit','telegram_explicit']}},'L2_PERSONAL_WRITE',
            lambda content,source_type:self.long_term_memory.capture_allowed(content,source_type))
        add('update_memory','Update a selected personal memory with new provenance.',
            {'memory_id':s(80),'content':s(2000)},'L2_PERSONAL_WRITE',self.long_term_memory.update)
        add('forget_memory','Forget one selected personal memory.',{'memory_id':s(80)},'L2_PERSONAL_WRITE',self.long_term_memory.forget)
        add('find_file','Search active indexed files by content or title.',{'query':s(1000)},'L0_READ',self.retrieval.search)
        add('list_documents','List active indexed notes without their bodies.',
            {'limit':{'type':'integer','minimum':1,'maximum':100,'required':False}},'L0_READ',
            lambda limit=30:self._list_indexed_documents(limit))
        add('search_web','Search the web with cited results.',{'query':s(1000)},'L0_READ',
            self.research.run if self.research else off,bool(self.research and self.research.enabled))
        add('get_current_selection','Read this tab’s short-lived H.O.L.O context.',{'session_id':s(100)},'L0_READ',
            lambda session_id:self._session_context(session_id))
        add('read_email','Read a Gmail thread by provider ID.',{'thread_id':s(200)},'L0_READ',self.gmail.thread)
        add('search_email','Search inbox metadata in Gmail.',{'query':s(300),'limit':{'type':'integer','minimum':1,'maximum':50,'required':False}},'L0_READ',
            lambda query,limit=20:self.gmail.list_messages('search',query,limit))
        add('draft_email','Create a Gmail draft; sending is a separate action.',
            {'to':s(320),'subject':s(300),'body':s(20000)},'L2_PERSONAL_WRITE',self.gmail.create_draft)
        add('send_email','Send a reviewed Gmail draft after an approval.',
            {'draft_id':s(200),'confirmation':s(240)},'L3_EXTERNAL_WRITE',self.gmail.send_draft)
        add('read_calendar','Read calendar events within an explicit range.',{'start':s(64),'end':s(64),'query':s(300,0,required=False)},
            'L0_READ',lambda start,end,query='':self.calendar.events(start,end,query))
        add('find_availability','Read Google Calendar free/busy for a range.',{'start':s(64),'end':s(64)},'L0_READ',self.calendar.availability)
        add('create_calendar_event','Create an event after approval.',{'summary':s(300),'start':s(64),'end':s(64),
            'description':s(5000,0,required=False),'confirmation':s(240)},'L3_EXTERNAL_WRITE',self.calendar.create)
        add('reschedule_calendar_event','Reschedule an event after approval.',{'event_id':s(200),'start':s(64),'end':s(64),'confirmation':s(240)},
            'L3_EXTERNAL_WRITE',self.calendar.reschedule)
        add('cancel_calendar_event','Cancel an event after approval.',{'event_id':s(200),'confirmation':s(240)},'L3_EXTERNAL_WRITE',self.calendar.cancel)
        add('start_focus','Start a local Focus Lock session.',active_focus,'L1_REVERSIBLE',
            lambda minutes,goal,allowed_apps=None,distractions=None:self.focus.start(minutes,goal,allowed_apps,distractions))
        for name in ('pause_focus','resume_focus','stop_focus'):
            method=getattr(self.focus,name.removesuffix('_focus'))
            add(name,name.replace('_',' ').capitalize()+' for the active local session.',{},'L1_REVERSIBLE',lambda method=method:method())
        add('capture_screen','Request one user-selected screen frame.',{'question':s(1000)},'L2_PERSONAL_WRITE',off,False)
        add('analyze_screen','Analyze a single explicitly captured frame.',{'question':s(1000),'image_data_url':s(700000)},'L2_PERSONAL_WRITE',off,False)
        invoice=obj({'seller':obj({'name':s(200),'address':s(1000),'email':s(320,0,required=False)},['name','address']),
            'customer':obj({'name':s(200),'address':s(1000),'email':s(320,0,required=False)},['name','address']),
            'currency':s(3,3),'invoice_number':s(40,0,required=False),'invoice_date':s(10,0,required=False),'due_date':s(10,0,required=False),
            'items':{'type':'array','maxItems':30,'items':obj({'description':s(500),'quantity':{'type':'number','minimum':0.0001,'maximum':100000},
                'unit_price':{'type':'number','minimum':0,'maximum':1000000000},'tax_rate':{'type':'number','minimum':0,'maximum':100,'required':False}},['description','quantity','unit_price'])},
            'source_ids':{'type':'array','items':s(80),'maxItems':30,'required':False}},['seller','customer','items'])
        add('create_invoice','Create a local invoice PDF draft after authorization.',{'data':invoice},'L2_PERSONAL_WRITE',lambda data:self.documents.create_invoice(data))
        add('create_document','Create a local report, summary or letter PDF.',{'kind':{'type':'string','enum':['report','summary','letter']},
            'title':s(200),'content':s(100000),'source_ids':{'type':'array','items':s(80),'maxItems':30,'required':False}},
            'L2_PERSONAL_WRITE',lambda kind,title,content,source_ids=None:self.documents.create_document(kind,title,content,source_ids))
        add('telegram_send','Send an approved, allowlisted Telegram artifact after explicit confirmation.',{'document_id':s(80),'user_id':s(32)},
            'L3_EXTERNAL_WRITE',off,False)
        windows={
            'open_application':({'application':s(120)},'L1_REVERSIBLE'),
            'open_file':({'path':s(1000)},'L1_REVERSIBLE'),
            'open_folder':({'path':s(1000)},'L1_REVERSIBLE'),
            'open_url':({'url':s(2048)},'L1_REVERSIBLE'),
            'get_active_application':({},'L0_READ'),'get_active_window':({},'L0_READ'),
            'set_volume':({'percent':{'type':'integer','minimum':0,'maximum':100}},'L1_REVERSIBLE')}
        for name,(arguments,permission) in windows.items():add(name,'Safe structured Windows operation; available in Phase 27.',arguments,permission,off,False)
        native_available=os.name=='nt'
        for name in ('open_application','open_file','open_folder','open_url','get_active_application','get_active_window','set_volume'):
            registry.tools[name].available=native_available
        registry.tools['open_application'].function=self.windows.open_application
        registry.tools['open_url'].function=lambda url:self.windows.open_url(url)
        registry.tools['open_file'].function=lambda path:self.windows.open_file(path)
        registry.tools['open_folder'].function=lambda path:self.windows.open_folder(path)
        registry.tools['get_active_application'].function=self.windows.get_active_application
        registry.tools['get_active_window'].function=self.windows.get_active_window
        registry.tools['set_volume'].function=self.windows.set_volume
        registry.preflight=self.windows.validate_request
        add('capture_screenshot','Use the explicit browser screen picker for one transient frame.',{},'L2_PERSONAL_WRITE',
            self.windows.capture_screenshot,False)
        add('open_latest_invoice','Open the most recently generated local invoice after authorization.',{},'L1_REVERSIBLE',
            self._open_latest_invoice,native_available)
        add('get_system_info','Read non-identifying runtime and platform information.',{},'L0_READ',self.windows.get_system_info)

    def _open_latest_invoice(self):
        with self.database.connect() as db:
            row=db.execute("SELECT relative_path FROM generated_documents WHERE kind='invoice' AND status='active' ORDER BY created_at DESC LIMIT 1").fetchone()
        if not row:raise ValueError('No active generated invoice is available')
        return self.windows.open_file(str((self.documents.generated_dir/row['relative_path']).resolve()))

    def _list_indexed_documents(self,limit=30):
        with self.database.connect() as db:
            rows=db.execute('''SELECT d.id,d.title,s.relative_path AS path,s.modified FROM documents d
                JOIN sources s ON s.id=d.source_id WHERE s.status='active' ORDER BY d.title LIMIT ?''',(max(1,min(int(limit),100)),)).fetchall()
        return {'documents':[dict(row) for row in rows]}

    def _session_context(self,session_id):
        _,context,_=self.sessions.get(session_id)
        return context.context_snapshot()

    def _execute_tool(self,name,arguments):
        try:return self.orchestrator.tools.execute(name,arguments)
        except PermissionError:
            pending=self.approvals.request(name,arguments)
            return {'ok':False,'tool':name,'result':None,'error':{'code':'APPROVAL_REQUIRED',
                'message':'This action needs your explicit approval.'},'verification':'NOT_RUN','approval':pending}
        except Exception as error:
            structured=getattr(error,'result',None)
            if structured is not None:return structured
            raise

    def health(self):
        return {'ok': True, 'service': 'Jarvis', 'camera_required': False,
                'microphone_required': False, 'mode': 'configured' if self.brain.enabled else 'local',
                'model':self.brain.model, 'embeddings_enabled':self.embeddings.enabled}

    def settings_status(self):
        try:
            with self.database.connect() as db:
                database_ok=db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
                sources=db.execute("SELECT count(*) FROM sources WHERE status='active'").fetchone()[0]
            database_state='CONNECTED' if database_ok else 'ERROR'
        except Exception:database_state='ERROR';database_ok=False;sources=0
        gmail=self.gmail.status();calendar=self.calendar.status();telegram=self.telegram.status();focus=self.focus.status()
        active_windows=all(self.orchestrator.tools.tools[name].available for name in
            ('open_application','open_file','open_folder','open_url','get_active_application','get_active_window','set_volume'))
        provider_sources=self.provider_events.status()
        integrations=[
            {'name':'OPENAI / ASTRA','status':'CONNECTED' if self.brain.enabled else 'ACTION REQUIRED',
             'detail':self.brain.model if self.brain.enabled else 'Configure an API key locally for live Astra.'},
            {'name':'SECOND BRAIN','status':database_state,'detail':f'{sources} indexed source(s); SQLite quick check '+('passed' if database_ok else 'failed')},
            {'name':'VOICE','status':'ACTION REQUIRED','detail':'Browser speech support and microphone permission are checked only after you press Use browser voice.'},
            {'name':'WAKE WORD','status':'DISABLED','detail':'Opt-in per browser tab. Microphone access is released when disabled.'},
            {'name':'SCREEN','status':'CONNECTED' if self.vision.enabled else 'ACTION REQUIRED',
             'detail':'One-shot capture is user initiated; screenshots are not stored.' if self.vision.enabled else 'Configure authorized vision access locally; capture remains opt-in.'},
            {'name':'CAMERA','status':'ACTION REQUIRED','detail':'Optional. Availability is checked after Look at this once; startup never requests camera access.'},
            {'name':'FOCUS LOCK','status':'CONNECTED' if focus.get('monitor_supported') else 'ACTION REQUIRED',
             'detail':focus.get('state','IDLE')+' · '+('local timer and foreground monitor ready' if focus.get('monitor_supported') else 'local timer available; foreground monitor unavailable')},
            {'name':'GMAIL','status':'CONNECTED' if gmail.get('connected') else 'ACTION REQUIRED',
             'detail':'Google OAuth configured; sending still requires approval.' if gmail.get('connected') else 'Configure local Google OAuth credentials and authorize Gmail.'},
            {'name':'CALENDAR','status':'CONNECTED' if calendar.get('connected') else 'ACTION REQUIRED',
             'detail':'Google OAuth configured; changes still require approval.' if calendar.get('connected') else 'Configure local Google OAuth credentials and authorize Calendar.'},
            {'name':'TELEGRAM','status':'CONNECTED' if telegram.get('running') else ('ERROR' if telegram.get('state')=='ERROR' else ('DISABLED' if not telegram.get('enabled') else ('ACTION REQUIRED' if not telegram.get('configured') else 'CONNECTED'))),
             'detail':f"{telegram.get('allowed_user_count',0)} allowlisted user(s); token is never returned."},
            {'name':'WINDOWS TOOLS','status':'CONNECTED' if active_windows else 'ACTION REQUIRED',
             'detail':'Allowlisted app/file/browser actions, read-only foreground checks and approved master-volume control; screen capture uses the explicit browser picker; no shell tool is available.' if active_windows else 'Structured Windows controls are unavailable on this platform; no shell tool is available.'},
            {'name':'AUTOMATIONS','status':'DISABLED','detail':'Automations are off until you explicitly enable an individual rule.'},
            {'name':'GMAIL EVENT SOURCE','status':provider_sources['GMAIL']['status'],
             'detail':('Read-only important-mail polling; '+('enabled' if provider_sources['GMAIL']['enabled'] else 'disabled')+
                       f"; {provider_sources['GMAIL']['poll_interval_seconds']} second interval; message content is not retained.")},
            {'name':'CALENDAR EVENT SOURCE','status':provider_sources['CALENDAR']['status'],
             'detail':('Read-only upcoming-event polling; '+('enabled' if provider_sources['CALENDAR']['enabled'] else 'disabled')+
                       f"; {provider_sources['CALENDAR']['poll_interval_seconds']} second interval; event content is not retained.")},
        ]
        return {'integrations':integrations,'diagnostics':{'provider_available':self.brain.enabled,
            'database_healthy':database_ok,'indexing_status':'READY' if not self.index_result.get('errors') else 'PARTIAL',
            'indexed_sources':sources,'microphone':'CHECKS AFTER USER GESTURE','camera':'CHECKS AFTER USER GESTURE',
            'last_successful_sync':None,'last_successful_use':None},
            'setup_guide':'See docs/SETUP.md for local credential setup. Do not paste secrets into chat.'}

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
        if method == 'GET' and path == '/api/settings/status':return self.settings_status()
        if method == 'GET' and path == '/api/automations':
            result=self.automations.list();result['provider_sources']=self.provider_events.status();return result
        if method == 'GET' and path == '/api/tools':
            return {'tools':self.orchestrator.tools.definitions(),'shell_available':False}
        if method == 'GET' and path == '/api/cards':return self.cards.list(query.get('all',[''])[0]=='1')
        if method == 'POST' and path == '/api/cards/save':
            return {'card':self.cards.save(data.get('card_type'),data.get('title'),data.get('payload',{}),data.get('source_id',''))}
        if method == 'POST' and path == '/api/cards/temporary':
            return {'card':self.cards.add_temporary(data.get('card_type'),data.get('title'),data.get('payload',{}),data.get('source_id',''))}
        if method == 'POST' and path == '/api/cards/action':
            return {'card':self.cards.action(data.get('id'),data.get('action'))}
        if method == 'GET' and path == '/api/approvals':
            return self.approvals.list_pending()
        if method == 'POST' and path == '/api/approvals/request':
            context={}
            session_id=data.get('session_id')
            if isinstance(session_id,str) and session_id:
                _,session_context,_=self.sessions.get(session_id);context=session_context.context_snapshot()
            return {'approval':self.approvals.request(data.get('tool'),data.get('arguments',{}),context)}
        if method == 'POST' and path == '/api/approvals/confirm':
            return self.approvals.confirm(data.get('approval_id'),data.get('confirmation'))
        if method == 'POST' and path == '/api/approvals/reject':
            return {'approval':self.approvals.reject(data.get('approval_id'))}
        if method == 'POST' and path == '/api/automations':return {'automation':self.automations.create(data)}
        if method == 'POST' and path == '/api/automations/update':
            return {'automation':self.automations.update(data.get('id'),data.get('automation'))}
        if method == 'POST' and path in ('/api/automations/enable','/api/automations/disable'):
            return {'automation':self.automations.set_enabled(data.get('id'),path.endswith('/enable'))}
        if method == 'POST' and path == '/api/automations/delete':return self.automations.delete(data.get('id'))
        if method == 'POST' and path == '/api/automations/run-due':return self.automations.run_due()
        if method == 'POST' and path == '/api/automations/provider-source':
            return {'source':self.provider_events.configure(data.get('provider'),data.get('enabled'))}
        if method == 'POST' and path == '/api/tools/execute':
            return self._execute_tool(data.get('name'),data.get('arguments',{}))
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
            return self._execute_tool('send_email',{'draft_id':data.get('draft_id'),'confirmation':data.get('confirmation')})
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
            return self._execute_tool('create_calendar_event',{key:data[key] for key in ('summary','start','end','confirmation') if key in data} | {'description':data.get('description','')})
        if method == 'POST' and path == '/api/calendar/reschedule':
            return self._execute_tool('reschedule_calendar_event',{key:data[key] for key in ('event_id','start','end','confirmation') if key in data})
        if method == 'POST' and path == '/api/calendar/cancel':
            return self._execute_tool('cancel_calendar_event',{key:data[key] for key in ('event_id','confirmation') if key in data})
        if method == 'POST' and path == '/api/focus/start':
            result=self.focus.start(data.get('minutes',90),data.get('goal','Focus session'),data.get('allowed_apps'),data.get('distractions'))
            self.automations.emit_event('FOCUS_STARTED')
            self.automations.emit_state('FOCUS_ACTIVE')
            return result
        if method == 'POST' and path == '/api/focus/pause':
            result=self.focus.pause();self.automations.emit_state('FOCUS_PAUSED');return result
        if method == 'POST' and path == '/api/focus/resume':
            result=self.focus.resume();self.automations.emit_state('FOCUS_ACTIVE');return result
        if method == 'POST' and path == '/api/focus/stop':
            result=self.focus.stop();self.automations.emit_event('FOCUS_ENDED');return result
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
