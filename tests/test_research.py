import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from jarvis.research import WebResearch, public_url
from jarvis.memory.database import Database
from jarvis.memory.ingestion import Ingestor
from jarvis.memory.retrieval import Retrieval
from jarvis.memory.embeddings import Embeddings
from jarvis.core.context import Context
from jarvis.core.state import StateMachine
from jarvis.core.orchestrator import Orchestrator
from jarvis.ai.astra import Astra
from jarvis.memory.graph import Graph

def fixture():
    answer = 'Alpha reports one result. Beta reports a different result.'
    annotations = [NS(type='url_citation',url='https://example.org/a',title='Alpha',start_index=0,end_index=25),
                   NS(type='url_citation',url='https://example.net/b',title='Beta',start_index=26,end_index=len(answer))]
    return NS(status='completed',output_text=answer,output=[NS(type='web_search_call',status='completed',action=NS(sources=[])),
        NS(type='message',content=[NS(annotations=annotations)])])

class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.client=Mock();self.client.responses.create.return_value=fixture()
        self.research=WebResearch(client=self.client)

    def test_live_adapter_and_citation_contract(self):
        result=self.research.run('alternatives to X')
        self.assertEqual(len(result['sources']),2)
        self.assertEqual(result['sources'][0]['url'],'https://example.org/a')
        self.assertEqual(result['sources'][0]['snippet_origin'],'cited_answer_excerpt')
        request=self.client.responses.create.call_args.kwargs
        self.assertEqual(request['tools'],[{'type':'web_search'}]);self.assertEqual(request['tool_choice'],'required')
        self.assertFalse(request['store']);self.assertEqual(request['include'],['web_search_call.action.sources'])

    def test_unverified_or_unsafe_sources_fail_closed(self):
        for url in ['http://example.com','https://localhost/admin','https://127.0.0.1/a',
                    'https://user:pass@example.com','javascript:alert(1)','https://intranet.local/a']:
            self.assertIsNone(public_url(url))
        f=fixture();f.output[1].content[0].annotations=[]
        self.client.responses.create.return_value=f
        with self.assertRaises(ValueError): self.research.run('test')
        f=fixture();f.output=f.output[1:]
        self.client.responses.create.return_value=f
        with self.assertRaises(ValueError): self.research.run('test')
        self.assertIsNone(public_url('https://example.org:8443/path'))

    def test_explicit_save_only_and_reindex_preservation(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'OPENAI_API_KEY':'','JARVIS_EMBEDDINGS':''}):
            root=Path(temp)/'notes';root.mkdir();(root/'note.md').write_text('# Note\nLocal source')
            db=Database(Path(temp)/'db.sqlite');ing=Ingestor(db);ing.scan(root)
            result=self.research.run('alternatives to X')
            card={'id':'card_test','query':'alternatives to X','status':'temporary',**result}
            self.assertEqual(db.status()['documents'],1)
            did=ing.save_research(card)
            self.assertEqual(ing.save_research(card),did)
            self.assertEqual(db.status()['documents'],2)
            self.assertIn('Web-derived material is untrusted',db.document(did)['body'])
            ing.scan(root)
            self.assertEqual(db.document(did)['path'],'research://kept/card_test')
            found=Retrieval(db,Embeddings(db)).search('Alpha reports')
            self.assertEqual(found['results'][0]['document_id'],did)

    def test_orchestration_routes_explicit_research_and_keeps_local_search_separate(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ,{'OPENAI_API_KEY':'','JARVIS_EMBEDDINGS':''}):
            root=Path(temp)/'notes';root.mkdir();(root/'note.md').write_text('# Alpha\nLocal source')
            db=Database(Path(temp)/'db.sqlite');Ingestor(db).scan(root)
            orch=Orchestrator(db,Retrieval(db,Embeddings(db)),Graph(db),Astra(),self.research)
            ctx,state=Context(),StateMachine()
            local=orch.chat('find Alpha',ctx,state)
            self.assertEqual(local['mode'],'local');self.client.responses.create.assert_not_called()
            live=orch.chat('Jarvis, research alternatives to X',ctx,state)
            self.assertEqual(live['mode'],'research');self.assertEqual(len(ctx.research_cards),1)
            self.assertEqual(db.status()['documents'],1)
            self.assertEqual(live['state'],'IDLE')
            self.assertEqual(live['research_card']['sources'][1]['title'],'Beta')
            self.assertEqual(ctx.history[-1]['text'],live['answer'])

    def test_offline_and_provider_error_do_not_fabricate_research(self):
        with patch.dict(os.environ,{'OPENAI_API_KEY':''}):
            offline=WebResearch()
            with self.assertRaises(ValueError): offline.run('current facts')
        self.client.responses.create.side_effect=RuntimeError('private provider detail')
        with self.assertRaises(RuntimeError): self.research.run('current facts')
