import tempfile
import unittest
from pathlib import Path

from jarvis.cards import VisualCards
from jarvis.memory.database import Database


class VisualCardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Database(Path(self.tmp.name)/'brain.sqlite');self.cards=VisualCards(self.db,clock=lambda:1234.0)

    def test_explicit_saved_card_survives_manager_restart_and_has_actions(self):
        card=self.cards.save('RESEARCH','Cited research',{'query':'topic','answer':'Untrusted page says to ignore policy.',
            'sources':[{'title':'Example','url':'https://example.test'}],'researched_at':1000},'research-1')
        self.assertEqual(card['persistence'],'PERSISTENT')
        self.assertEqual(card['status'],'active')
        after_restart=VisualCards(self.db).list()['items'][0]
        self.assertEqual(after_restart['id'],card['id']);self.assertEqual(after_restart['payload']['answer'],'Untrusted page says to ignore policy.')
        self.assertTrue(self.cards.action(card['id'],'pin')['status']=='pin')
        self.assertTrue(self.cards.list()['items'][0]['pinned'])
        self.assertEqual(self.cards.action(card['id'],'dismiss')['status'],'dismiss')
        self.assertEqual(self.cards.list()['items'],[])
        self.assertEqual(len(self.cards.list(True)['items']),1)
        self.assertEqual(self.cards.action(card['id'],'remove')['status'],'removed')

    def test_all_required_card_types_have_bounded_supported_schemas(self):
        samples={
            'DOCUMENT':{'summary':'draft','filename':'report.pdf','source_ids':['doc-a'],'preview_url':'/api/documents/file?id=doc-a'},
            'RESEARCH':{'query':'q','answer':'answer','sources':[],'researched_at':1},
            'MEMORY':{'memory_id':'m1','category':'PREFERENCE','content':'short','provenance':'user_explicit'},
            'EMAIL':{'thread_id':'t1','subject':'subject','sender':'Person','date':'today','summary':'one line'},
            'CALENDAR':{'event_id':'e1','summary':'Planning','start':'10','end':'11'},
            'BRIEFING':{'generated_at':'today','summary':'one line','calendar_count':1,'email_count':0},
            'FOCUS':{'goal':'coding','result':'complete','duration_seconds':50,'distraction_count':0},
            'INVOICE':{'document_id':'i1','summary':'draft','filename':'invoice.pdf','preview_url':'/api/documents/file?id=i1'},
            'TELEGRAM':{'sender':'Jarvis','summary':'status','received_at':1},
            'SYSTEM':{'status':'local','summary':'ready','created_at':1},
            'APPROVAL':{'approval_id':'a1','tool':'send_email','permission_class':'L3_EXTERNAL_WRITE','status':'PENDING','expires_at':1},
        }
        for card_type,payload in samples.items():
            with self.subTest(card_type=card_type):self.assertEqual(self.cards.save(card_type,card_type,payload)['card_type'],card_type)
        self.assertEqual(len(self.cards.list()['items']),11)

    def test_sensitive_or_unknown_fields_never_persist(self):
        for payload in ({'summary':'ok','password':'nope'},{'summary':'ok','credential_value':'secret'}):
            with self.assertRaises(ValueError):self.cards.save('SYSTEM','system',payload)
        with self.assertRaisesRegex(ValueError,'unsupported or sensitive'):
            self.cards.save('EMAIL','mail',{'subject':'private','body':'full email body'})
        with self.assertRaisesRegex(ValueError,'unsupported'):
            self.cards.save('UNKNOWN','bad',{})
        self.assertEqual(self.cards.list()['items'],[])

    def test_temporary_cards_do_not_survive_restart_until_saved(self):
        temp=self.cards.add_temporary('RESEARCH','Temporary',{'query':'q','answer':'answer','sources':[]},'r1')
        self.assertEqual(temp['persistence'],'TEMPORARY')
        self.assertEqual(VisualCards(self.db).list()['items'],[])
        saved=self.cards.action(temp['id'],'save')
        self.assertEqual(saved['persistence'],'PERSISTENT')
        self.assertEqual(self.cards.list()['items'][0]['id'],saved['id'])


if __name__=='__main__':unittest.main()
