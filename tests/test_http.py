import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import server
from jarvis.core.runtime import Runtime

class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name); notes=root/'notes'; notes.mkdir()
        (notes/'voice.md').write_text('# Brand voice\nUse clear, warm language.',encoding='utf-8')
        (root/'holo.html').write_text('<title>HOLO</title>')
        (root/'ui').mkdir(); (root/'ui'/'app.js').write_text('/* safe */')
        env=patch.dict(os.environ,{'JARVIS_DATA_DIR':str(root/'data'),'OPENAI_API_KEY':'','JARVIS_EMBEDDINGS':''})
        env.start(); self.addCleanup(env.stop)
        runtime=Runtime(root,lambda:str(notes))
        for name,value in [('ROOT',str(root)),('RUNTIME',runtime),('notes_dir',lambda:str(notes))]:
            p=patch.object(server,name,value);p.start();self.addCleanup(p.stop)
        self.http=ThreadingHTTPServer(('127.0.0.1',0),server.H)
        self.thread=threading.Thread(target=self.http.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.http.server_close);self.addCleanup(self.http.shutdown)
        self.url=f'http://127.0.0.1:{self.http.server_port}'

    def request(self,path,data=None,headers=None):
        req=Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,
                    headers=({'Content-Type':'application/json'} if data is not None else {}) | (headers or {}))
        try:
            with urlopen(req,timeout=5) as r:return r.status,r.read()
        except HTTPError as e:return e.code,e.read()

    def test_baseline_and_memory_chat_flow(self):
        for route in ['/','/?sim=1','/?probe=1','/api/tree','/api/state','/api/health','/api/memory/status','/api/graph']:
            self.assertEqual(self.request(route)[0],200,route)
        self.assertEqual(self.request('/api/state',{'event':'grab','card':'voice'})[0],200)
        self.assertEqual(json.loads(self.request('/api/state')[1])['card'],'voice')
        sid=json.loads(self.request('/api/jarvis/session',{})[1])['session_id']
        result=json.loads(self.request('/api/jarvis/chat',{'session_id':sid,'message':'find brand voice'})[1])
        self.assertIn('sources',result)
        did=result['sources'][0]['document_id']
        self.assertEqual(self.request('/api/jarvis/context',{'session_id':sid,'document_id':did})[0],200)
        self.assertIn('Local extract',json.loads(self.request('/api/jarvis/chat',{'session_id':sid,'message':'summarize this'})[1])['answer'])
        self.assertEqual(self.request('/api/jarvis/chat',{'message':'no session'})[0],400)

    def test_origin_host_body_and_static_boundary(self):
        self.assertEqual(self.request('/api/memory/reindex',{}, {'Origin':'https://evil.test'})[0],403)
        self.assertEqual(self.request('/api/tree',headers={'Host':'evil.test'})[0],403)
        self.assertEqual(self.request('/api/tree',headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(self.request('/api/state',[],{})[0],400)
        self.assertEqual(self.request('/api/state',{'x':'x'*70000})[0],413)
        self.assertEqual(self.request('/api/state',{}, {'Content-Type':'text/plain'})[0],403)
        for route in ['/data/memory.sqlite','/.env','/ui/%2e%2e/server.py','/ui/..%5cdata%5cmemory.sqlite']:
            self.assertEqual(self.request(route)[0],404,route)
        self.assertEqual(self.request('/ui/app.js')[0],200)

    def test_research_card_requires_own_session_and_explicit_save(self):
        from types import SimpleNamespace as NS
        from unittest.mock import Mock
        from jarvis.research import WebResearch
        from jarvis.core.orchestrator import Orchestrator
        engine=Mock()
        answer='Alpha result. Beta result.'
        engine.responses.create.return_value=NS(status='completed',output_text=answer,
            output=[NS(type='web_search_call',status='completed'),NS(type='message',content=[NS(annotations=[
                NS(type='url_citation',url='https://example.org/a',title='Alpha',start_index=0,end_index=13),
                NS(type='url_citation',url='https://example.net/b',title='Beta',start_index=14,end_index=len(answer))])])])
        server.RUNTIME.research=WebResearch(client=engine)
        server.RUNTIME.orchestrator=Orchestrator(server.RUNTIME.database,server.RUNTIME.retrieval,
            server.RUNTIME.graph,server.RUNTIME.brain,server.RUNTIME.research)
        a=json.loads(self.request('/api/jarvis/session',{})[1])['session_id']
        b=json.loads(self.request('/api/jarvis/session',{})[1])['session_id']
        response=json.loads(self.request('/api/jarvis/chat',{'session_id':a,'message':'research alternatives to X'})[1])
        self.assertEqual(response['mode'],'research')
        card=response['research_card'];self.assertEqual(server.RUNTIME.database.status()['documents'],1)
        self.assertEqual(json.loads(self.request('/api/research/cards?session_id='+b)[1])['cards'],[])
        self.assertEqual(self.request('/api/research/card',{'session_id':b,'card_id':card['id'],'action':'save'})[0],400)
        self.assertEqual(self.request('/api/research/card',{'session_id':a,'card_id':card['id'],'action':'keep'})[0],200)
        saved=json.loads(self.request('/api/research/card',{'session_id':a,'card_id':card['id'],'action':'save'})[1])
        self.assertEqual(server.RUNTIME.database.document(saved['document_id'])['source_id'][:7],'source_')
        self.assertEqual(self.request('/api/memory/reindex',{})[0],200)
        self.assertEqual(server.RUNTIME.database.status()['active_sources'],2)
        self.assertEqual(self.request('/api/research/card',{'session_id':a,'card_id':card['id'],'action':'dismiss'})[0],200)
        self.assertEqual(json.loads(self.request('/api/research/cards?session_id='+a)[1])['cards'],[])
        self.assertEqual(server.RUNTIME.database.status()['active_sources'],2)

    def test_explicit_screen_vision_is_transient_and_session_free(self):
        from unittest.mock import Mock
        server.RUNTIME.vision=Mock()
        server.RUNTIME.vision.analyze_frame.return_value={
            'answer':'The screen shows an error.', 'observations':['Error dialog'], 'caution':''}
        initial=server.RUNTIME.database.status()['documents']
        payload={'question':'Explain this screen','image_data_url':'data:image/jpeg;base64,/9j/eA=='}
        status,raw=self.request('/api/vision/screen',payload)
        self.assertEqual(status,200);self.assertEqual(json.loads(raw)['answer'],'The screen shows an error.')
        server.RUNTIME.vision.analyze_frame.assert_called_once_with(payload['question'],payload['image_data_url'])
        camera={'question':'What am I holding?','image_data_url':payload['image_data_url']}
        self.assertEqual(self.request('/api/vision/camera',camera)[0],200)
        server.RUNTIME.vision.analyze_frame.assert_called_with(camera['question'],camera['image_data_url'])
        self.assertEqual(server.RUNTIME.database.status()['documents'],initial)

    def test_focus_lock_routes_keep_session_actions_explicit(self):
        from unittest.mock import Mock
        server.RUNTIME.focus=Mock()
        server.RUNTIME.focus.status.return_value={'state':'IDLE'}
        server.RUNTIME.focus.start.return_value={'state':'ACTIVE','distraction_count':0}
        server.RUNTIME.focus.pause.return_value={'state':'PAUSED'}
        server.RUNTIME.focus.resume.return_value={'state':'ACTIVE'}
        server.RUNTIME.focus.stop.return_value={'state':'STOPPED'}
        self.assertEqual(json.loads(self.request('/api/focus')[1])['state'],'IDLE')
        start={'minutes':90,'goal':'Coding','allowed_apps':['code.exe'],'distractions':['instagram']}
        self.assertEqual(json.loads(self.request('/api/focus/start',start)[1])['state'],'ACTIVE')
        server.RUNTIME.focus.start.assert_called_once_with(90,'Coding',['code.exe'],['instagram'])
        self.assertEqual(json.loads(self.request('/api/focus/pause',{})[1])['state'],'PAUSED')
        self.assertEqual(json.loads(self.request('/api/focus/resume',{})[1])['state'],'ACTIVE')
        self.assertEqual(json.loads(self.request('/api/focus/stop',{})[1])['state'],'STOPPED')

    def test_gmail_integration_status_and_send_confirmation_route(self):
        from unittest.mock import Mock
        server.RUNTIME.gmail=Mock()
        server.RUNTIME.gmail.status.return_value={'state':'NOT CONNECTED','connected':False}
        server.RUNTIME.gmail.send_draft.return_value={'id':'sent1','threadId':'t1'}
        self.assertEqual(json.loads(self.request('/api/integrations/gmail')[1])['state'],'NOT CONNECTED')
        body={'draft_id':'d1','confirmation':'SEND d1'}
        self.assertEqual(json.loads(self.request('/api/gmail/send',body)[1])['id'],'sent1')
        server.RUNTIME.gmail.send_draft.assert_called_once_with('d1','SEND d1')
