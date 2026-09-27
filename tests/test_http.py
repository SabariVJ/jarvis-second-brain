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
