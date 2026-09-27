"""Grounded request orchestration shared by text and voice transcripts."""
import re
from jarvis.ai.astra import local_summary
from jarvis.tools import Registry, Tool

class Orchestrator:
    def __init__(self, database, retrieval, graph, brain):
        self.database, self.retrieval, self.graph, self.brain = database,retrieval,graph,brain
        self.tools = Registry()
        self.tools.register(Tool('search_memory',0,{'query':str},retrieval.search))
        self.tools.register(Tool('read_document',0,{'doc_id':str},database.document))

    def chat(self, message, context, state, selected_id=None, spoken=False):
        if not isinstance(message,str) or not message.strip() or len(message)>4000:
            raise ValueError('Message must contain 1–4000 characters')
        if not context.lock.acquire(False): raise ValueError('A response is already running in this tab')
        try:
            if state.state.value not in ('IDLE','OFFLINE','ERROR','INTERRUPTED'):
                state.transition('INTERRUPTED'); state.transition('IDLE')
            state.transition('RETRIEVING')
            if selected_id:
                self.database.document(selected_id)  # validate identity, never trust title/body from browser
                context.select(selected_id)
            selected = context.selection()
            q = re.sub(r'^\s*jarvis[,\s]*','',message.strip(), flags=re.I).lower()
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
            return self._finish(answer,used,node_ids,state,mode,warning,action)
        except Exception:
            state.transition('ERROR')
            raise
        finally:
            context.lock.release()

    def _local(self, sources, summary):
        if summary:
            return 'Local extract (AI is unavailable):\n' + local_summary(sources[0]['text'])
        return 'Found these indexed sources:\n' + '\n'.join(f"• {s['title']} — {s['relative_path']}\n  {s['text'][:220]}" for s in sources[:5])

    def _finish(self, answer, sources, node_ids, state, mode, warning, action='focus'):
        state.transition('IDLE')
        citations = [{k:s[k] for k in ('document_id','source_id','title','path','relative_path','start','end') if k in s} for s in sources]
        return {'answer':answer,'sources':citations,'node_ids':node_ids,'mode':mode,
                'warning':warning,'action':action,**state.snapshot()}
