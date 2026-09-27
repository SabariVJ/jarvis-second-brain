from datetime import datetime,timezone
import tempfile
import unittest
from pathlib import Path
from pypdf import PdfReader

from jarvis.memory.database import Database
from jarvis.documents import DocumentAutomation


class DocumentAutomationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name);self.db=Database(root/'memory.sqlite')
        self.now=datetime(2026,9,28,10,0,tzinfo=timezone.utc)
        self.docs=DocumentAutomation(self.db,root/'data',clock=lambda:self.now)

    def invoice(self,**changes):
        data={'seller':{'name':'North Star Studio','address':'42 Sample Road, Pune, India','email':'billing@example.test'},
            'customer':{'name':'Company X','address':'11 Client Street, Mumbai','email':'accounts@example.test'},
            'currency':'INR','invoice_date':'2026-09-28','due_date':'2026-10-28','invoice_number':'INV-TEST-001',
            'items':[{'description':'App development & delivery','quantity':'1','unit_price':'25000','tax_rate':''}]}
        data.update(changes);return data

    def test_natural_language_prepare_collects_missing_fields_without_creating_a_file(self):
        result=self.docs.prepare_invoice_from_text('Create an invoice for Company X for ₹25,000 for app development.')
        self.assertFalse(result['ready']);self.assertEqual(result['draft']['customer']['name'],'Company X')
        self.assertEqual(result['draft']['items'][0]['unit_price'],'25000')
        self.assertIn('Your business name',result['missing_fields']);self.assertIn('Customer address',result['missing_fields'])
        self.assertFalse(self.docs.generated_dir.exists())

    def test_complete_invoice_creates_extractable_pdf_and_decimal_totals(self):
        result=self.docs.create_invoice(self.invoice())
        artifact=self.docs.read_file(result['id']);self.assertTrue(artifact['content'].startswith(b'%PDF'))
        with PdfReader(self.docs.generated_dir/result['filename']) as pdf:
            self.assertGreaterEqual(len(pdf.pages),1);text='\n'.join(page.extract_text() or '' for page in pdf.pages)
        self.assertIn('INV-TEST-001',text);self.assertIn('25000.00',text);self.assertIn('App development & delivery',text)
        self.assertEqual(result['invoice']['subtotal'],'25000.00');self.assertEqual(result['invoice']['total'],'25000.00')
        self.assertEqual(result['invoice']['tax_total'],'0.00');self.assertTrue(result['filename'].endswith('.pdf'))

    def test_tax_is_only_added_when_explicitly_supplied_and_rounding_is_stable(self):
        data=self.invoice(invoice_number='INV-TAX',items=[{'description':'Consulting','quantity':'3','unit_price':'0.34','tax_rate':'7.5'}])
        result=self.docs.create_invoice(data)
        self.assertEqual(result['invoice']['subtotal'],'1.02');self.assertEqual(result['invoice']['tax_total'],'0.08');self.assertEqual(result['invoice']['total'],'1.10')

    def test_validation_prevents_partial_invoice_and_arbitrary_values(self):
        with self.assertRaisesRegex(ValueError,'needs:'):self.docs.create_invoice({'seller':{},'customer':{},'items':[]})
        for changes in ({'currency':'US$'}, {'invoice_date':'not-a-date'},
            {'items':[{'description':'Work','quantity':'-1','unit_price':'2'}]},
            {'items':[{'description':'Work','quantity':'1','unit_price':'NaN'}]},
            {'items':[{'description':'Work','quantity':'1','unit_price':'0.335'}]},
            {'items':[{'description':'Work','quantity':'1','unit_price':'2','tax_rate':'101'}]}):
            with self.assertRaises(ValueError):self.docs.create_invoice(self.invoice(**changes))

    def test_duplicate_invoice_number_never_overwrites_or_leaves_orphan_file(self):
        first=self.docs.create_invoice(self.invoice())
        with self.assertRaises(Exception):self.docs.create_invoice(self.invoice())
        self.assertEqual(len(list(self.docs.generated_dir.glob('*.pdf'))),1)
        self.assertEqual(self.docs.read_file(first['id'])['content'][:4],b'%PDF')

    def test_automatic_invoice_numbers_are_unique(self):
        first=self.docs.create_invoice(self.invoice(invoice_number=''))
        second=self.docs.create_invoice(self.invoice(invoice_number=''))
        self.assertEqual(first['invoice']['invoice_number'],'INV-20260928-0001')
        self.assertEqual(second['invoice']['invoice_number'],'INV-20260928-0002')

    def test_generic_report_supports_long_content_and_source_provenance(self):
        source_id='doc-source'
        with self.db.connect() as db:
            db.execute("INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)",(source_id,'notes','/private/plan.md','plan.md','fp',1,1,'active',None,'text/markdown'))
            db.execute("INSERT INTO documents VALUES(?,?,?,?,?)",(source_id,source_id,'Project plan','Grounded plan text','fp'))
        content='Quarterly execution notes.\n\n'+('Clear evidence and next steps. '*1500)
        result=self.docs.create_document('report','Quarterly report',content,[source_id])
        with PdfReader(self.docs.generated_dir/result['filename']) as pdf:
            self.assertGreater(len(pdf.pages),1);text='\n'.join(page.extract_text() or '' for page in pdf.pages)
        self.assertIn('Quarterly report',text);self.assertIn('plan.md',text)
        self.assertEqual(result['source_ids'],[source_id])
        with self.assertRaises(ValueError):self.docs.create_document('letter','Unsafe','body',['../../outside'])

    def test_local_share_approval_and_telegram_artifact_lookup_are_separate(self):
        card=self.docs.create_invoice(self.invoice())
        self.assertIsNone(self.docs.telegram_artifact('latest'))
        with self.assertRaisesRegex(ValueError,'Exact share approval'):self.docs.action(card['id'],'approve_share')
        approved=self.docs.action(card['id'],'approve_share','APPROVE SHARE '+card['id'])
        self.assertTrue(approved['share_approved'])
        selected=self.docs.telegram_artifact('latest')
        self.assertEqual(selected['id'],card['id']);self.assertNotIn('content',selected)
        with_bytes=self.docs.telegram_artifact(card['id'],True)
        self.assertTrue(with_bytes['content'].startswith(b'%PDF'))
        self.docs.action(card['id'],'revoke_share')
        self.assertIsNone(self.docs.telegram_artifact('latest'))

    def test_integrity_and_path_checks_protect_open_and_share(self):
        card=self.docs.create_invoice(self.invoice())
        path=self.docs.generated_dir/card['filename'];path.write_bytes(b'%PDF-corrupt')
        with self.assertRaisesRegex(ValueError,'integrity'):self.docs.read_file(card['id'])
        self.docs.action(card['id'],'approve_share','APPROVE SHARE '+card['id'])
        self.assertIsNone(self.docs.telegram_artifact(card['id'],True))
        with self.db.connect() as db:db.execute("UPDATE generated_documents SET relative_path='../../outside.pdf' WHERE id=?",(card['id'],))
        with self.assertRaisesRegex(ValueError,'path'):self.docs.read_file(card['id'])

    def test_pin_dismiss_and_generic_document_types(self):
        cards=[self.docs.create_document(kind,kind.title(),'Created with wrapped text.\n\n'+('detail '*300)) for kind in ('report','summary','letter')]
        self.assertEqual(len(self.docs.list_documents()['items']),3)
        pinned=self.docs.action(cards[0]['id'],'pin');self.assertTrue(pinned['pinned'])
        self.docs.action(cards[-1]['id'],'dismiss')
        self.assertEqual(len(self.docs.list_documents()['items']),2)
        self.assertEqual(self.docs.action(cards[1]['id'],'save')['saved_locally'],True)


if __name__=='__main__':unittest.main()
