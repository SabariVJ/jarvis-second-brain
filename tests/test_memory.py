import tempfile
import unittest
from pathlib import Path
from jarvis.memory.database import Database, stable_id
from jarvis.memory.ingestion import Ingestor, chunks
from jarvis.memory.graph import Graph

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'notes'; self.root.mkdir()
        self.db = Database(Path(self.tmp.name)/'memory.sqlite')
        self.ingest = Ingestor(self.db)

    def test_incremental_change_delete_and_provenance(self):
        note = self.root/'training.md'
        note.write_text('# Training\n\nSVJ uses [[Progressive Overload]]. #fitness', encoding='utf-8')
        original = note.read_bytes()
        self.assertEqual(self.ingest.scan(self.root)['indexed'],1)
        self.assertEqual(note.read_bytes(),original)
        self.assertEqual(self.ingest.scan(self.root)['unchanged'],1)
        did = stable_id('doc',str(note.resolve()))
        self.assertEqual(self.db.document(did)['body'],original.decode())
        graph = Graph(self.db).snapshot(did)
        self.assertEqual(len(graph['edges']),3)
        self.assertTrue(all(e['source_id'] and e['evidence'] for e in graph['edges']))
        note.write_text('# Changed\nOther content',encoding='utf-8')
        self.assertEqual(self.ingest.scan(self.root)['indexed'],1)
        self.assertEqual(len(Graph(self.db).snapshot()['edges']),1)
        note.unlink(); self.assertEqual(self.ingest.scan(self.root)['deleted'],1)
        with self.assertRaises(ValueError): self.db.document(did)
        self.assertFalse(Graph(self.db).snapshot()['nodes'])

    def test_duplicate_paths_preserved_without_reindex_duplicates(self):
        for name in ['a.md','b.md']: (self.root/name).write_text('# Same\nExact duplicate')
        self.ingest.scan(self.root); self.ingest.scan(self.root)
        self.assertEqual(self.db.status()['documents'],2)
        self.assertEqual(self.db.status()['chunks'],2)

    def test_chunks_cover_source_and_are_bounded(self):
        body = ('First sentence. More detail.\n\n' * 800)
        parts = list(chunks(body))
        self.assertEqual(parts[0][0],0); self.assertEqual(parts[-1][1],len(body))
        for start,end,text in parts:
            self.assertEqual(text,body[start:end]); self.assertLessEqual(len(text),1400)
        self.assertTrue(all(b[0] <= a[1] for a,b in zip(parts,parts[1:])))

    def test_error_and_unavailable_root_preserve_history(self):
        (self.root/'bad.pdf').write_bytes(b'not a PDF')
        self.assertEqual(len(self.ingest.scan(self.root)['errors']),1)
        with self.assertRaises(ValueError): self.ingest.scan(self.root/'missing')
        self.assertEqual(len(self.db.status()['errors']),1)

    def test_schema_enforces_provenance(self):
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError), self.db.connect() as db:
            db.execute("INSERT INTO memories(id,category,content,source_id,created,confidence) VALUES ('m','FACT','unsupported','no-source',0,1)")

    def test_graph_bounded_and_focus_outside_initial_page(self):
        for i in range(12): (self.root/f'{i}.md').write_text(f'# Topic {i}\n[[Shared]]')
        self.ingest.scan(self.root)
        graph=Graph(self.db).snapshot(limit=6)
        self.assertLessEqual(len(graph['nodes']),6);self.assertTrue(graph['has_more'])
        did=stable_id('doc',str((self.root/'9.md').resolve()))
        focused=Graph(self.db).snapshot(focus=did,limit=6)
        self.assertIn(did,[n['id'] for n in focused['nodes']])
        ids={n['id'] for n in focused['nodes']}
        self.assertTrue(all(e['subject'] in ids and e['object'] in ids for e in focused['edges']))
