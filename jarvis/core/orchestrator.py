"""Grounded request orchestration shared by text and voice transcripts."""
import re
import secrets
from jarvis.ai.astra import local_summary
from jarvis.tools import Registry, Tool, ToolPermissionError, ToolError

class Orchestrator:
    def __init__(self, database, retrieval, graph, brain, research=None, long_term_memory=None, document_service=None):
        self.database, self.retrieval, self.graph, self.brain = database,retrieval,graph,brain
        self.research = research
        self.long_term_memory=long_term_memory
        self.document_service=document_service
        self.approvals=None
        self.tools = Registry(authorizer=self._authorize_explicit_memory_tool)
        self.tools.register(Tool('search_memory',0,{'query':str},retrieval.search))
        self.tools.register(Tool('read_document',0,{'doc_id':str},database.document))
        if research:
            self.tools.register(Tool('web_research',0,{'query':str},research.run))
        if long_term_memory:
            self.tools.register(Tool('search_personal_memory',0,{'query':str},long_term_memory.search))
            self.tools.register(Tool('inspect_memory',0,{'memory_id':str},long_term_memory.inspect))
            self.tools.register(Tool('remember',2,function=lambda content,source_type:long_term_memory.capture_allowed(content,source_type),
                arguments={'content':{'type':'string','maxLength':2000},'source_type':{'type':'string','enum':['user_explicit','telegram_explicit']}},
                description='Save a clear personal fact only after an explicit user remember command.'))
            self.tools.register(Tool('update_memory',2,{'memory_id':str,'content':str},long_term_memory.update,
                description='Update one selected personal memory while preserving provenance.'))
            self.tools.register(Tool('forget_memory',2,{'memory_id':str},long_term_memory.forget,
                description='Forget one selected personal memory on an explicit user request.'))

    @staticmethod
    def _authorize_explicit_memory_tool(tool,args,authorization):
        return authorization=='explicit_user_memory_command' and tool.name in {'remember','update_memory','forget_memory'}

    def _memory_write(self,name,args,context):
        if self.approvals:
            return self.approvals.execute_explicit_user_command(name,args,context.context_snapshot())['tool_result']['result']
        return self.tools.execute(name,args,authorization='explicit_user_memory_command')['result']

    def chat(self, message, context, state, selected_id=None, spoken=False, capture_memories=True, origin='local'):
        if not isinstance(message,str) or not message.strip() or len(message)>4000:
            raise ValueError('Message must contain 1–4000 characters')
        if not context.lock.acquire(False): raise ValueError('A response is already running in this tab')
        try:
            if state.state.value not in ('IDLE','OFFLINE','ERROR','INTERRUPTED'):
                state.transition('INTERRUPTED'); state.transition('IDLE')
            state.transition('RETRIEVING')
            q = re.sub(r'^\s*jarvis[,\s]*','',message.strip(), flags=re.I).lower()
            windows_request=self._windows_intent(message)
            if windows_request:
                name,args=windows_request
                try:
                    result=self.tools.execute(name,args)['result']
                    state.transition('THINKING')
                    return self._finish(self._windows_text(name,result),[],[],state,'windows_tool',None)
                except ToolPermissionError:
                    state.transition('THINKING')
                    pending=self.approvals.request(name,args,context.context_snapshot()) if self.approvals else None
                    answer='I staged this Windows action in Action Approvals. Review and approve it before it runs.'
                    response=self._finish(answer,[],[],state,'approval_required',None)
                    if pending:response['approval']=pending
                    return response
                except ToolError as error:
                    state.transition('THINKING')
                    return self._finish(error.result['error']['message'],[],[],state,'windows_tool_unavailable',None)
                except Exception:
                    state.transition('THINKING')
                    return self._finish('Windows could not complete that action. No shell command was run.',[],[],state,'windows_tool_error',None)
            research_match = re.match(r'^(?:research|search (?:the )?web(?: for)?|look up (?:the latest )?information (?:on|about))\s+(.+)$',q)
            if research_match:
                query = research_match.group(1).strip()
                if not self.research or not self.research.enabled:
                    state.transition('THINKING')
                    state.transition('OFFLINE')
                    return self._finish('Live research needs an OpenAI API key. Your local notes are still available.',[],[],state,'research_unavailable',None)
                state.transition('TOOL_RUNNING')
                try:
                    data = self.tools.execute('web_research',{'query':query})['result']
                except Exception:
                    state.transition('THINKING')
                    state.transition('OFFLINE')
                    return self._finish('Live research failed or had no verifiable citations. Please try again later.',[],[],state,'research_unavailable',None)
                state.transition('THINKING')
                card = {'id':secrets.token_urlsafe(18),'query':query,'status':'temporary',**data}
                if len(context.research_cards) >= 20:
                    oldest = next((key for key,c in context.research_cards.items() if c['status']=='temporary'),None)
                    if oldest: del context.research_cards[oldest]
                    else:
                        return self._finish('Your research cards are full. Dismiss one before searching again.',[],[],state,'research_limit',None)
                context.research_cards[card['id']] = card
                context.history.extend([{'role':'user','text':message},{'role':'assistant','text':data['answer']}])
                context.history[:] = context.history[-6:]
                result = self._finish(data['answer'],[],[],state,'research',data['warning'])
                result['research_card']=card
                return result
            if self.document_service and re.search(r'\b(?:create|make|prepare)\s+(?:an?\s+)?invoice\b',q):
                draft=self.document_service.prepare_invoice_from_text(message)
                state.transition('THINKING')
                missing=draft['missing_fields']
                answer=('I prepared the invoice details. Add: '+', '.join(missing)+'. The PDF will be saved only after you submit the completed form.'
                    if missing else 'The invoice details are complete. Review them and confirm creation in the local document card.')
                result=self._finish(answer,[],[],state,'document_draft',None)
                result['document_action']={'kind':'invoice_prepare',**draft};return result
            memory_action=self._memory_action(message,context,state,origin)
            if memory_action is not None:return memory_action
            captured=None
            if self.long_term_memory and capture_memories:
                captured=self.long_term_memory.capture_significant(message)
                if captured and captured.get('id'):context.last_memory_id=captured['id']
            if selected_id:
                self.database.document(selected_id)  # validate identity, never trust title/body from browser
                context.select(selected_id)
            selected = context.selection()
            summary = bool(re.search(r'\b(summarize|summarise|summary|explain)\b',q))
            followup = bool(re.search(r'\b(this|it|that)\b',q)) or q.rstrip('.?') in ('show related notes','where is it stored','summarize','summarise','summary')
            sources, mode, warning = [], 'keyword', None
            if selected and followup:
                d = self.tools.execute('read_document',{'doc_id':selected})['result']
                sources = [{'document_id':d['id'],'source_id':d['source_id'],'title':d['title'],
                            'path':d['path'],'relative_path':d['relative_path'],'text':d['body'][:80000],
                            'node_id':d['id'],'score':1, 'start':0,'end':min(80000,len(d['body']))}]
                if len(d['body']) > 80000: warning = 'Summary covers the first 80,000 characters of this source.'
            elif summary and re.search(r'\b(this|it|that)\b',q):
                return self._finish('Select a note first, then ask me to summarize it.',[],[],state,'local',None)
            else:
                found = self.tools.execute('search_memory',{'query':message})['result']
                sources,mode,warning = found['results'],found['mode'],found['warning']
                if sources: context.select(sources[0]['document_id'])
            personal_memories=[]
            if self.long_term_memory:
                search_text=re.sub(r'\b(?:jarvis|please|can you|could you|what|which|tell me|about|from|the|my|is|are|do|i)\b',' ',q)
                try:personal_memories=self.long_term_memory.search(search_text,limit=3)
                except ValueError:personal_memories=[]
                if personal_memories:context.last_memory_id=personal_memories[0]['id']
            if summary and sources:
                doc = self.database.document(sources[0]['document_id'])
                sources = [{**sources[0], 'text':doc['body'][:80000], 'start':0, 'end':min(80000,len(doc['body']))}]
                if len(doc['body']) > 80000: warning = 'Summary covers the first 80,000 characters of this source.'
            state.transition('THINKING')
            action = 'focus'
            node_ids = [s['document_id'] for s in sources]
            if q.startswith('open') and sources:
                action = 'open'
                answer = f"Source ready to open: {sources[0]['relative_path']}."
                used = sources[:1]
            elif 'stored' in q and sources:
                answer = sources[0]['path']; used = sources[:1]
            elif 'related' in q and selected:
                graph = self.graph.snapshot(selected)
                node_ids = [n['id'] for n in graph['nodes']]
                answer = 'Showing source-supported connections. Select an edge to see its evidence.'
                used = sources
            elif not sources:
                if personal_memories:
                    answer='From your personal long-term memory (not indexed document knowledge): '+personal_memories[0]['content']
                    mode='personal_memory';used=[]
                else:
                    answer = 'I could not find a supporting source in the indexed notes. Try another phrase or reindex the notes folder.'
                    used = []
            elif self.brain.enabled:
                try:
                    result = self.brain.answer(message,sources,context.history,spoken)
                    answer = result['answer']; used = [s for s in sources if s['document_id'] in result['citations']]
                    mode = 'astra'
                except Exception:
                    warning = 'AI response unavailable or ungrounded; using a local extract.'
                    answer = self._local(sources,summary); used = sources[:1] if summary else sources
                    mode = 'local'
                    state.transition('OFFLINE')
            else:
                answer = self._local(sources,summary); used = sources[:1] if summary else sources
                mode = 'local'
            context.history.extend([{'role':'user','text':message}, {'role':'assistant','text':answer}])
            context.history[:] = context.history[-6:]
            result=self._finish(answer,used,node_ids,state,mode,warning,action)
            result['personal_memories']=personal_memories
            if captured:result['memory_saved']={'id':captured['id'],'duplicate':captured.get('duplicate',False),'category':captured['category']}
            return result
        except Exception:
            state.transition('ERROR')
            raise
        finally:
            context.lock.release()

    def _memory_action(self,message,context,state,origin):
        memory=self.long_term_memory
        if not memory:return None
        raw=re.sub(r'^\s*jarvis[,\s]*','',message.strip(),flags=re.I)
        if not raw:return None
        explicit=re.match(r'^(?:please\s+)?remember(?:\s+that)?\s+(.+?)\s*[.!?]*$',raw,re.I)
        if explicit:
            source_type='telegram_explicit' if origin=='telegram' else 'user_explicit'
            item=self._memory_write('remember',{'content':explicit.group(1),'source_type':source_type},context);context.last_memory_id=item['id']
            message_text='I already have this memory; it remains from your explicit request.' if item.get('duplicate') else 'I saved this intentional personal memory.'
            result=self._finish(message_text,[],[],state,'personal_memory',None);result['memory']=item;return result
        if re.match(r'^(?:don.t|do not) remember this\.?$',raw,re.I):
            return self._finish("I don't save ordinary conversation automatically. No stored memory was changed.",[],[],state,'personal_memory',None)
        no_remember=re.match(r'^(?:don.t|do not) remember (?:that\s+)?(.+?)\s*[.!?]*$',raw,re.I)
        if no_remember:
            target=no_remember.group(1)
            category='PREFERENCE' if 'preference' in target.casefold() else None
            target=re.sub(r'^(?:my\s+)?(?:preference\s+(?:for|about)\s+|that\s+)','',target,flags=re.I)
            matches=self.tools.execute('search_personal_memory',{'query':target})['result']
            matches=[item for item in matches if not category or item['category']==category][:3]
            if len(matches)==1:
                result=self._memory_write('forget_memory',{'memory_id':matches[0]['id']},context);context.last_memory_id=None
                return self._finish('I deleted that stored personal memory.',[],[],state,'personal_memory',None)
            return self._finish('I did not find one unambiguous stored memory to delete.',[],[],state,'personal_memory',None)
        if re.match(r'^(?:why do you know that|show why you know that)\??$',raw,re.I):
            if not context.last_memory_id:return self._finish('Select or search for a personal memory first, then ask why I know it.',[],[],state,'personal_memory',None)
            item=self.tools.execute('inspect_memory',{'memory_id':context.last_memory_id})['result']
            result=self._finish(f"This is a {item['category'].lower()} memory from {item['source']['reference']} (recorded {item['created_at']}).",[],[],state,'personal_memory',None)
            result['memory']=item;return result
        recall=re.match(r'^(?:what do you remember about|show memories related to|what do you remember regarding)\s+(.+?)\??$',raw,re.I)
        if recall:
            items=self.tools.execute('search_personal_memory',{'query':recall.group(1)})['result'][:10]
            if not items:return self._finish('I do not have a matching personal memory. This is separate from searching indexed documents.',[],[],state,'personal_memory',None)
            context.last_memory_id=items[0]['id']
            answer='Personal long-term memories (separate from indexed documents):\n'+ '\n'.join(
                f"• [{x['category']}] {x['content']} — source: {x['source']['reference']}" for x in items)
            result=self._finish(answer,[],[],state,'personal_memory',None);result['personal_memories']=items;return result
        corrected=re.match(r'^(?:update what you remember about\s+(.+?)\s+to\s+|update memory\s+(.+?)\s+to\s+)(.+?)\s*[.!?]*$',raw,re.I)
        if corrected:
            query=corrected.group(1) or corrected.group(2);replacement=corrected.group(3)
            matches=self.tools.execute('search_personal_memory',{'query':query})['result'][:3]
            if len(matches)!=1:return self._finish('I need one matching memory before I can update it. Search or inspect the memory first.',[],[],state,'personal_memory',None)
            item=self._memory_write('update_memory',{'memory_id':matches[0]['id'],'content':replacement},context);context.last_memory_id=item['id']
            result=self._finish('I updated that personal memory and kept its provenance.',[],[],state,'personal_memory',None);result['memory']=item;return result
        corrected=re.match(r'^(?:correct that memory|update that memory)(?:\s+to|\s*:)?\s+(.+?)\s*[.!?]*$',raw,re.I)
        if corrected:
            if not context.last_memory_id:return self._finish('Search for a personal memory before correcting it.',[],[],state,'personal_memory',None)
            item=self._memory_write('update_memory',{'memory_id':context.last_memory_id,'content':corrected.group(1)},context);context.last_memory_id=item['id']
            result=self._finish('I corrected that personal memory and updated its provenance.',[],[],state,'personal_memory',None);result['memory']=item;return result
        forget=re.match(r'^(?:forget|delete)\s+(.+?)\s*[.!?]*$',raw,re.I)
        if forget:
            target=forget.group(1).casefold()
            if target in ('this memory','that memory','this','that','it'):
                memory_id=context.last_memory_id
                if not memory_id:return self._finish('Search for the memory you want to forget, then ask me to forget it.',[],[],state,'personal_memory',None)
            else:
                category='PREFERENCE' if 'preference' in target else None
                search=re.sub(r'^(?:my\s+)?(?:saved\s+)?(?:preference\s+(?:for|about)\s+)?','',target)
                search=re.sub(r'^that\s+','',search)
                matches=self.tools.execute('search_personal_memory',{'query':search})['result']
                matches=[item for item in matches if not category or item['category']==category][:3]
                if len(matches)!=1:return self._finish('I need one matching memory before I can forget it. Search or inspect the memory first.',[],[],state,'personal_memory',None)
                memory_id=matches[0]['id']
            self._memory_write('forget_memory',{'memory_id':memory_id},context);context.last_memory_id=None
            return self._finish('I deleted that personal memory.',[],[],state,'personal_memory',None)
        return None

    @staticmethod
    def _windows_intent(message):
        raw=re.sub(r'^\s*jarvis[,\s]*','',message.strip(),flags=re.I)
        if re.fullmatch(r'(?:what application am i using|what app am i using|which application is active|what is in the foreground)\??',raw,re.I):
            return 'get_active_application',{}
        if re.fullmatch(r'open (?:the )?(?:latest )?invoice\.?',raw,re.I):return 'open_latest_invoice',{}
        match=re.fullmatch(r'(?:set|change) (?:the )?(?:master )?volume to (\d{1,3})(?:\s*percent|%)?\.?',raw,re.I)
        if match:return 'set_volume',{'percent':int(match.group(1))}
        match=re.fullmatch(r'open (?:application )?(.+?)(?:\s+app)?\.?',raw,re.I)
        if match and match.group(1).strip().casefold() in {'vs code','visual studio code','vscode','notepad','text editor','file explorer','explorer','edge','microsoft edge','chrome','google chrome'}:
            return 'open_application',{'application':match.group(1).strip()}
        match=re.fullmatch(r'open (?:url )?(https?://\S+)',raw,re.I)
        if match:return 'open_url',{'url':match.group(1)}
        match=re.fullmatch(r'open (?:file )(.+)',raw,re.I)
        if match:return 'open_file',{'path':match.group(1).strip().strip('"')}
        match=re.fullmatch(r'open folder (.+)',raw,re.I)
        if match:return 'open_folder',{'path':match.group(1).strip().strip('"')}
        return None

    @staticmethod
    def _windows_text(name,result):
        if name=='get_active_application':return 'The active application is '+(result.get('application') or 'unknown')+'.'
        if name=='get_active_window':return 'The active window is '+(result.get('title') or 'untitled')+'.'
        return 'Windows confirmed the open action for '+str(result.get('application') or result.get('path') or result.get('url') or 'the requested item')+'.'

    def _local(self, sources, summary):
        if summary:
            return 'Local extract (AI is unavailable):\n' + local_summary(sources[0]['text'])
        return 'Found these indexed sources:\n' + '\n'.join(f"• {s['title']} — {s['relative_path']}\n  {s['text'][:220]}" for s in sources[:5])

    def _finish(self, answer, sources, node_ids, state, mode, warning, action='focus'):
        state.transition('IDLE')
        citations = [{k:s[k] for k in ('document_id','source_id','title','path','relative_path','start','end') if k in s} for s in sources]
        return {'answer':answer,'sources':citations,'node_ids':node_ids,'mode':mode,
                'warning':warning,'action':action,**state.snapshot()}
