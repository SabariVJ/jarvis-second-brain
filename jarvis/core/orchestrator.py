"""Grounded request orchestration shared by text and voice transcripts."""
import re
import secrets
from jarvis.ai.astra import local_summary
from jarvis.tools import Registry, Tool

class Orchestrator:
    def __init__(self, database, retrieval, graph, brain, research=None, long_term_memory=None):
        self.database, self.retrieval, self.graph, self.brain = database,retrieval,graph,brain
        self.research = research
        self.long_term_memory=long_term_memory
        self.tools = Registry()
        self.tools.register(Tool('search_memory',0,{'query':str},retrieval.search))
        self.tools.register(Tool('read_document',0,{'doc_id':str},database.document))
        if research:
            self.tools.register(Tool('web_research',0,{'query':str},research.run))

    def chat(self, message, context, state, selected_id=None, spoken=False, capture_memories=True, origin='local'):
        if not isinstance(message,str) or not message.strip() or len(message)>4000:
            raise ValueError('Message must contain 1–4000 characters')
        if not context.lock.acquire(False): raise ValueError('A response is already running in this tab')
        try:
            if state.state.value not in ('IDLE','OFFLINE','ERROR','INTERRUPTED'):
                state.transition('INTERRUPTED'); state.transition('IDLE')
            state.transition('RETRIEVING')
            q = re.sub(r'^\s*jarvis[,\s]*','',message.strip(), flags=re.I).lower()
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
                    warning = 'OpenAI response unavailable or ungrounded; using a local extract.'
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
            item=memory.capture_allowed(explicit.group(1),source_type);context.last_memory_id=item['id']
            message_text='I already have this memory; it remains from your explicit request.' if item.get('duplicate') else 'I saved this intentional personal memory.'
            result=self._finish(message_text,[],[],state,'personal_memory',None);result['memory']=item;return result
        if re.match(r'^(?:don.t|do not) remember this\.?$',raw,re.I):
            return self._finish("I don't save ordinary conversation automatically. No stored memory was changed.",[],[],state,'personal_memory',None)
        no_remember=re.match(r'^(?:don.t|do not) remember (?:that\s+)?(.+?)\s*[.!?]*$',raw,re.I)
        if no_remember:
            target=no_remember.group(1)
            category='PREFERENCE' if 'preference' in target.casefold() else None
            target=re.sub(r'^(?:my\s+)?(?:preference\s+(?:for|about)\s+|that\s+)','',target,flags=re.I)
            matches=memory.search(target,category=category,limit=3)
            if len(matches)==1:
                result=memory.forget(matches[0]['id']);context.last_memory_id=None
                return self._finish('I deleted that stored personal memory.',[],[],state,'personal_memory',None)
            return self._finish('I did not find one unambiguous stored memory to delete.',[],[],state,'personal_memory',None)
        if re.match(r'^(?:why do you know that|show why you know that)\??$',raw,re.I):
            if not context.last_memory_id:return self._finish('Select or search for a personal memory first, then ask why I know it.',[],[],state,'personal_memory',None)
            item=memory.inspect(context.last_memory_id)
            result=self._finish(f"This is a {item['category'].lower()} memory from {item['source']['reference']} (recorded {item['created_at']}).",[],[],state,'personal_memory',None)
            result['memory']=item;return result
        recall=re.match(r'^(?:what do you remember about|show memories related to|what do you remember regarding)\s+(.+?)\??$',raw,re.I)
        if recall:
            items=memory.search(recall.group(1),limit=10)
            if not items:return self._finish('I do not have a matching personal memory. This is separate from searching indexed documents.',[],[],state,'personal_memory',None)
            context.last_memory_id=items[0]['id']
            answer='Personal long-term memories (separate from indexed documents):\n'+ '\n'.join(
                f"• [{x['category']}] {x['content']} — source: {x['source']['reference']}" for x in items)
            result=self._finish(answer,[],[],state,'personal_memory',None);result['personal_memories']=items;return result
        corrected=re.match(r'^(?:update what you remember about\s+(.+?)\s+to\s+|update memory\s+(.+?)\s+to\s+)(.+?)\s*[.!?]*$',raw,re.I)
        if corrected:
            query=corrected.group(1) or corrected.group(2);replacement=corrected.group(3)
            matches=memory.search(query,limit=3)
            if len(matches)!=1:return self._finish('I need one matching memory before I can update it. Search or inspect the memory first.',[],[],state,'personal_memory',None)
            item=memory.update(matches[0]['id'],replacement);context.last_memory_id=item['id']
            result=self._finish('I updated that personal memory and kept its provenance.',[],[],state,'personal_memory',None);result['memory']=item;return result
        corrected=re.match(r'^(?:correct that memory|update that memory)(?:\s+to|\s*:)?\s+(.+?)\s*[.!?]*$',raw,re.I)
        if corrected:
            if not context.last_memory_id:return self._finish('Search for a personal memory before correcting it.',[],[],state,'personal_memory',None)
            item=memory.update(context.last_memory_id,corrected.group(1));context.last_memory_id=item['id']
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
                matches=memory.search(search,category=category,limit=3)
                if len(matches)!=1:return self._finish('I need one matching memory before I can forget it. Search or inspect the memory first.',[],[],state,'personal_memory',None)
                memory_id=matches[0]['id']
            memory.forget(memory_id);context.last_memory_id=None
            return self._finish('I deleted that personal memory.',[],[],state,'personal_memory',None)
        return None

    def _local(self, sources, summary):
        if summary:
            return 'Local extract (AI is unavailable):\n' + local_summary(sources[0]['text'])
        return 'Found these indexed sources:\n' + '\n'.join(f"• {s['title']} — {s['relative_path']}\n  {s['text'][:220]}" for s in sources[:5])

    def _finish(self, answer, sources, node_ids, state, mode, warning, action='focus'):
        state.transition('IDLE')
        citations = [{k:s[k] for k in ('document_id','source_id','title','path','relative_path','start','end') if k in s} for s in sources]
        return {'answer':answer,'sources':citations,'node_ids':node_ids,'mode':mode,
                'warning':warning,'action':action,**state.snapshot()}
