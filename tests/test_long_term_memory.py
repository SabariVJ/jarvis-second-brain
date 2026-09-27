import sqlite3
import tempfile
import unittest
from pathlib import Path

from jarvis.memory.database import Database
from jarvis.memory.long_term import LongTermMemory


class LongTermMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Database(Path(self.tmp.name)/'memory.sqlite')
        self.now=[1_800_000_000.0]
        self.mem=LongTermMemory(self.db,lambda:self.now[0])

    def test_explicit_remember_records_complete_provenance(self):
        item=self.mem.capture_allowed('I prefer concise answers.','user_explicit')
        self.assertEqual(item['category'],'PREFERENCE')
        self.assertEqual(item['source']['type'],'user_explicit')
        self.assertIn('explicitly requested',item['source']['reference'])
        self.assertEqual(item['status'],'active')
        with self.db.connect() as db:
            source=db.execute('SELECT path,status FROM sources WHERE id=?',(item['id'],)).fetchone()
        self.assertEqual(source['path'],'jarvis-memory://'+item['id']);self.assertEqual(source['status'],'active')

    def test_conservative_significance_and_insignificant_rejection(self):
        item=self.mem.capture_significant('I prefer short email replies.')
        self.assertEqual(item['category'],'PREFERENCE')
        self.assertIsNone(self.mem.capture_significant('Hello Jarvis, how are you?'))
        self.assertIsNone(self.mem.capture_significant('I think perhaps a new project could be nice.'))

    def test_duplicate_prevention_and_normalized_search_category_filter(self):
        first=self.mem.remember('I prefer concise replies.','PREFERENCE')
        duplicate=self.mem.remember(' i PREFER concise   replies ','PREFERENCE')
        self.assertTrue(duplicate['duplicate']);self.assertEqual(first['id'],duplicate['id'])
        self.mem.remember('SVJ uses Supabase.','PROJECT')
        matches=self.mem.search('concise replies')
        self.assertEqual([m['id'] for m in matches],[first['id']])
        projects=self.mem.search('',category='PROJECT')
        self.assertEqual(projects[0]['content'],'SVJ uses Supabase.')
        self.assertIsNotNone(self.mem.inspect(first['id'])['last_used_at'])

    def test_update_correction_and_forget_mutate_persistent_state(self):
        item=self.mem.remember('We decided to ship monthly.','DECISION')
        corrected=self.mem.update(item['id'],'We decided to ship every two weeks.')
        self.assertIn('two weeks',corrected['content']);self.assertEqual(corrected['source']['type'],'user_update')
        with self.db.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0],1)
        result=self.mem.forget(item['id']);self.assertTrue(result['forgotten'])
        with self.db.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM memories').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT status FROM sources WHERE id=?',(item['id'],)).fetchone()[0],'deleted')
        with self.assertRaisesRegex(ValueError,'not found'):self.mem.inspect(item['id'])

    def test_expiration_is_excluded(self):
        item=self.mem.remember('The workshop is tomorrow.','EPISODE',expires_at=self.now[0]+1)
        self.now[0]+=2
        self.assertEqual(self.mem.search('workshop'),[])
        with self.assertRaisesRegex(ValueError,'expired'):self.mem.inspect(item['id'])

    def test_secrets_and_external_sources_are_rejected(self):
        for content in ('My password is correct-horse-battery','API key: sk-abcdefghijklmnopqrstuv','bot token 123456:abcdefghijklmnopqrstuvwxyz'):
            with self.assertRaisesRegex(ValueError,'secrets'):
                self.mem.capture_allowed(content,'user_explicit')
        for source in ('document','email','web','screen','telegram','assistant'):
            with self.assertRaisesRegex(ValueError,'user-authored'):
                self.mem.remember('An external source said this.',source_type=source)
        with self.assertRaisesRegex(ValueError,'explicit user'):
            self.mem.capture_allowed('Email says save me.','email')

    def test_schema_v1_migrates_existing_memory_without_losing_provenance(self):
        path=Path(self.tmp.name)/'legacy.sqlite'
        db=sqlite3.connect(path)
        try:
            db.executescript('''CREATE TABLE sources(id TEXT PRIMARY KEY,root TEXT NOT NULL,path TEXT NOT NULL UNIQUE,
                relative_path TEXT NOT NULL,fingerprint TEXT NOT NULL,modified REAL NOT NULL,indexed REAL NOT NULL,
                status TEXT NOT NULL,error TEXT,media_type TEXT NOT NULL);
                CREATE TABLE memories(id TEXT PRIMARY KEY,category TEXT NOT NULL,content TEXT NOT NULL,
                source_id TEXT NOT NULL REFERENCES sources(id),created REAL NOT NULL,confidence REAL NOT NULL);
                INSERT INTO sources VALUES('doc-source','notes','C:/notes/preferences.md','preferences.md','fp',1,1,'active',NULL,'text/markdown');
                INSERT INTO memories VALUES('old','PREFERENCE','I prefer clear answers.','doc-source',1,.9);
                PRAGMA user_version=1;''')
        finally:db.close()
        migrated=Database(path);items=LongTermMemory(migrated,lambda:100).search('clear answers')
        self.assertEqual(items[0]['id'],'old');self.assertEqual(items[0]['source']['type'],'document')
        with migrated.connect() as db:self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0],4)


if __name__=='__main__':unittest.main()
