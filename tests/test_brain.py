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
