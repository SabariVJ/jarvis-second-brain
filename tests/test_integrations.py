"""Actual installed SDK and PDF parser, with no network and synthetic source text."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from jarvis.ai.astra import Astra
from jarvis.memory.ingestion import pdf_reader

class IntegrationTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec('openai'), 'Install requirements.txt for SDK contract test')
    def test_official_sdk_serialization_and_response_parsing(self):
        import httpx
        from openai import OpenAI
        requests=[]
        def handle(request):
            payload=json.loads(request.content);requests.append(payload)
            return httpx.Response(200,json={'id':'resp_test','object':'response','created_at':0,
                'status':'completed','model':'gpt-6-astra','output':[{'type':'message','id':'msg_test',
                'role':'assistant','status':'completed','content':[{'type':'output_text','annotations':[],
                'text':json.dumps({'answer':'A grounded summary.','citations':['doc_test']})}]}]})
        with OpenAI(api_key='test-placeholder',http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
            result=Astra(client).answer('summarize this',[{'document_id':'doc_test','title':'Test','text':'Source evidence.'}])
        self.assertEqual(result['citations'],['doc_test'])
        self.assertFalse(requests[0]['store']);self.assertEqual(requests[0]['text']['format']['type'],'json_schema')

    @unittest.skipUnless(importlib.util.find_spec('openai'), 'Install requirements.txt for hosted search SDK test')
    def test_hosted_web_search_sdk_wire_contract(self):
        import httpx
        from openai import OpenAI
        from jarvis.research import WebResearch
        captured=[]
        answer='Alpha reports one result. Beta reports another.'
        def handle(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200,json={'id':'resp_web_test','object':'response','created_at':0,
                'status':'completed','model':'gpt-6-astra','output':[
                    {'type':'web_search_call','id':'ws_test','status':'completed','action':{'type':'search','queries':['alternatives'],'sources':[
                        {'url':'https://example.org/a'},{'url':'https://example.net/b'}]}},
                    {'type':'message','id':'msg_web','role':'assistant','status':'completed','content':[{'type':'output_text',
                        'text':answer,'annotations':[
                            {'type':'url_citation','url':'https://example.org/a','title':'Alpha','start_index':0,'end_index':25},
                            {'type':'url_citation','url':'https://example.net/b','title':'Beta','start_index':26,'end_index':len(answer)}]}]}]})
        with OpenAI(api_key='test-placeholder',http_client=httpx.Client(transport=httpx.MockTransport(handle))) as client:
            result=WebResearch(client=client).run('alternatives to X')
        self.assertEqual(len(result['sources']),2)
        self.assertEqual(captured[0]['tools'],[{'type':'web_search'}])
        self.assertEqual(captured[0]['tool_choice'],'required')
        self.assertFalse(captured[0]['store'])

    @unittest.skipUnless(importlib.util.find_spec('pypdf'), 'Install requirements.txt for PDF extraction test')
    def test_pdf_extracts_actual_text(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'training.pdf';writer=PdfWriter();page=writer.add_blank_page(width=612,height=792)
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 72 720 Td (SVJ training improves strength.) Tj ET')
            page[NameObject('/Contents')]=writer._add_object(stream)
            with path.open('wb') as f:writer.write(f)
            text=pdf_reader(path)
            self.assertIn('[Page 1]',text);self.assertIn('SVJ training improves strength.',text)
