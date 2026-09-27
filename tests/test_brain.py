import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from jarvis.memory.database import Database
from jarvis.memory.ingestion import Ingestor
from jarvis.memory.embeddings import Embeddings
from jarvis.memory.retrieval import Retrieval
from jarvis.memory.graph import Graph
from jarvis.ai.astra import Astra
from jarvis.core.context import Context
from jarvis.core.state import StateMachine
from jarvis.core.orchestrator import Orchestrator
from jarvis.tools import Registry, Tool
from jarvis.memory.long_term import LongTermMemory

class BrainTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ,{'OPENAI_API_KEY':'','JARVIS_EMBEDDINGS':''}); self.env.start(); self.addCleanup(self.env.stop)
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'notes'; self.root.mkdir()
        (self.root/'workout.md').write_text('# SVJ Training\nIncrease resistance gradually each week. Track recovery. [[Strength]]',encoding='utf-8')
        (self.root/'identity.md').write_text('# Brand voice\nWrite clear, direct, warm messages. Avoid jargon.',encoding='utf-8')
        self.db = Database(Path(self.tmp.name)/'db.sqlite'); Ingestor(self.db).scan(self.root)
        self.emb = Embeddings(self.db); self.search = Retrieval(self.db,self.emb)
        self.brain = Astra(); self.graph = Graph(self.db)
        self.orch = Orchestrator(self.db,self.search,self.graph,self.brain)
        self.ctx,self.state = Context(),StateMachine()

    def test_keyword_filename_fuzzy_and_no_false_sources(self):
        for q in ['SVJ','brand voice','workuot']:
            self.assertTrue(self.search.search(q)['results'])
        self.assertFalse(self.search.search('xylophonemeteor')['results'])
        self.assertFalse(self.search.search('" OR * (')['results'])

    def test_semantic_paraphrase_with_mocked_vectors(self):
        client = Mock()
        def embed(**kw):
            return NS(data=[NS(index=i,embedding=[1.,0.] if ('resistance' in t or 'muscle' in t) else [0.,1.]) for i,t in enumerate(kw['input'])])
        client.embeddings.create.side_effect = embed
        self.emb.client = client
        self.assertEqual(self.emb.index()['embedded'],2)
        self.assertEqual(self.emb.index()['embedded'],0)
        found = self.search.search('muscle progression')
        self.assertEqual(found['mode'],'hybrid')
        self.assertEqual(found['results'][0]['title'],'SVJ Training')

    def test_followups_selection_and_source_summary(self):
        r = self.orch.chat('Find my brand voice',self.ctx,self.state)
        did = r['sources'][0]['document_id']
        summary = self.orch.chat('Summarize it',self.ctx,self.state)
        self.assertEqual(summary['sources'][0]['document_id'],did)
        self.assertIn('warm',summary['answer'])
        opened = self.orch.chat('Open it',self.ctx,self.state)
        self.assertEqual(opened['action'],'open')
        self.assertIn('identity.md',self.orch.chat('Where is it stored?',self.ctx,self.state)['answer'])
        self.assertIn(did,self.orch.chat('Show related notes',self.ctx,self.state)['node_ids'])

    def test_missing_selection_and_deleted_source(self):
        self.assertIn('Select a note',self.orch.chat('Summarize this',self.ctx,self.state)['answer'])
        self.orch.chat('brand voice',self.ctx,self.state)
        (self.root/'identity.md').unlink(); Ingestor(self.db).scan(self.root)
        with self.assertRaises(ValueError): self.orch.chat('Summarize it',self.ctx,self.state)
        self.assertEqual(self.state.state.value,'ERROR')

    def test_named_summary_does_not_use_previous_selection(self):
        self.orch.chat('brand voice',self.ctx,self.state)
        result = self.orch.chat('Summarize SVJ training',self.ctx,self.state)
        self.assertEqual(result['sources'][0]['title'],'SVJ Training')

    def test_astra_contract_citations_and_injection_boundary(self):
        source = self.search.search('brand voice')['results'][0]
        client = Mock(); self.brain.client = client
        client.responses.create.return_value = NS(status='completed',output_text=json.dumps({'answer':'Clear and warm.','citations':[source['document_id']]}))
        result = self.orch.chat('Summarize this',self.ctx,self.state,source['document_id'])
        self.assertEqual(result['mode'],'astra')
        request = client.responses.create.call_args.kwargs
        self.assertEqual(request['model'],'gpt-6-astra'); self.assertFalse(request['store'])
        self.assertNotIn('tools',request); self.assertIn('untrusted_sources',request['input'][0]['content'])
        client.responses.create.return_value.output_text = '{"answer":"made up","citations":["fake"]}'
        result = self.orch.chat('Summarize this',self.ctx,self.state)
        self.assertEqual(result['mode'],'local'); self.assertNotIn('made up',result['answer'])
        client.responses.create.side_effect = RuntimeError('sk-secret')
        result = self.orch.chat('Summarize this',self.ctx,self.state)
        self.assertNotIn('sk-secret',str(result)); self.assertEqual(result['state'],'IDLE')

    def test_tool_permissions_and_arguments(self):
        r = Registry(); callback = Mock()
        r.register(Tool('send',3,{'text':str},callback))
        with self.assertRaises(PermissionError): r.execute('send',{'text':'a'})
        with self.assertRaises(ValueError): r.execute('send',{'text':'a','approved':True})
        callback.assert_not_called()

    def test_intentional_personal_memory_commands_provenance_update_and_forget(self):
        memory=LongTermMemory(self.db)
        orch=Orchestrator(self.db,self.search,self.graph,self.brain,long_term_memory=memory)
        saved=orch.chat('Remember that I prefer concise answers.',self.ctx,self.state)
        self.assertEqual(saved['mode'],'personal_memory');self.assertEqual(saved['memory']['category'],'PREFERENCE')
        found=orch.chat('What do you remember about concise answers?',self.ctx,self.state)
        self.assertIn('personal long-term memories',found['answer'].lower())
        why=orch.chat('Why do you know that?',self.ctx,self.state)
        self.assertIn('explicitly requested',why['answer'])
        corrected=orch.chat('Correct that memory to I prefer short answers.',self.ctx,self.state)
        self.assertIn('corrected',corrected['answer'].lower())
        self.assertEqual(memory.inspect(saved['memory']['id'])['content'],'I prefer short answers')
        forgotten=orch.chat('Forget it.',self.ctx,self.state)
        self.assertIn('deleted',forgotten['answer'].lower())
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0],0)

    def test_significance_capture_is_narrow_and_external_text_never_auto_persists(self):
        memory=LongTermMemory(self.db);orch=Orchestrator(self.db,self.search,self.graph,self.brain,long_term_memory=memory)
        captured=orch.chat('I prefer brief answers.',self.ctx,self.state)
        self.assertEqual(captured['memory_saved']['category'],'PREFERENCE')
        orch.chat('Hello Jarvis.',self.ctx,self.state)
        orch.chat('I prefer unrequested external text.',self.ctx,self.state,capture_memories=False,origin='telegram')
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0],1)
        recall=orch.chat('What do you remember about brief answers?',self.ctx,self.state)
        self.assertEqual(recall['mode'],'personal_memory')
        self.assertIn('personal long-term memories',recall['answer'].lower())
