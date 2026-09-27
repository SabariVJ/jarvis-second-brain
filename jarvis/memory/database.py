"""SQLite source-of-truth. One connection per operation, WAL, foreign keys."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import hashlib

def stable_id(kind, value):
    return kind + '_' + hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]

SCHEMA = '''
CREATE TABLE IF NOT EXISTS sources (
 id TEXT PRIMARY KEY, root TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
 relative_path TEXT NOT NULL, fingerprint TEXT NOT NULL, modified REAL NOT NULL,
 indexed REAL NOT NULL, status TEXT NOT NULL CHECK(status IN ('active','deleted','error')),
 error TEXT, media_type TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL UNIQUE REFERENCES sources(id),
 title TEXT NOT NULL, body TEXT NOT NULL, fingerprint TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS document_fingerprint ON documents(fingerprint);
CREATE TABLE IF NOT EXISTS chunks (
 id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
 ordinal INTEGER NOT NULL, text TEXT NOT NULL, start INTEGER NOT NULL, end INTEGER NOT NULL,
 UNIQUE(document_id,ordinal));
CREATE VIRTUAL TABLE IF NOT EXISTS chunk_fts USING fts5(id UNINDEXED, text, title, path);
CREATE TABLE IF NOT EXISTS vectors (
 chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
 model TEXT NOT NULL, embedding TEXT NOT NULL, PRIMARY KEY(chunk_id, model));
CREATE TABLE IF NOT EXISTS entities (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
 UNIQUE(name,kind));
CREATE TABLE IF NOT EXISTS relationships (
 id TEXT PRIMARY KEY, subject TEXT NOT NULL, predicate TEXT NOT NULL, object TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES sources(id), evidence TEXT NOT NULL,
 confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1));
CREATE INDEX IF NOT EXISTS relationship_source ON relationships(source_id);
CREATE TABLE IF NOT EXISTS memories (
 id TEXT PRIMARY KEY, category TEXT NOT NULL, content TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES sources(id), created REAL NOT NULL,
 confidence REAL NOT NULL CHECK(confidence BETWEEN 0 AND 1),
 normalized TEXT NOT NULL DEFAULT '', source_type TEXT NOT NULL DEFAULT 'document',
 source_reference TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL DEFAULT 0,
 importance REAL NOT NULL DEFAULT 0.5, last_used_at REAL, expires_at REAL,
 status TEXT NOT NULL DEFAULT 'active');
CREATE TABLE IF NOT EXISTS conversations (
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(id), created REAL NOT NULL,
 content TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, status TEXT NOT NULL,
 source_id TEXT NOT NULL REFERENCES sources(id));
CREATE TABLE IF NOT EXISTS projects (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id));
CREATE TABLE IF NOT EXISTS people (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id));
CREATE TABLE IF NOT EXISTS generated_documents (
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, title TEXT NOT NULL, filename TEXT NOT NULL,
 relative_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, mime_type TEXT NOT NULL,
 created_at REAL NOT NULL, invoice_number TEXT UNIQUE, source_ids TEXT NOT NULL DEFAULT '[]',
 data_json TEXT NOT NULL DEFAULT '{}', summary TEXT NOT NULL DEFAULT '',
 share_approved INTEGER NOT NULL DEFAULT 0, pinned INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','dismissed')));
CREATE INDEX IF NOT EXISTS generated_documents_latest ON generated_documents(status,created_at DESC);
CREATE TABLE IF NOT EXISTS approvals (
 id TEXT PRIMARY KEY, tool TEXT NOT NULL, arguments_json TEXT NOT NULL, arguments_sha256 TEXT NOT NULL,
 permission_class TEXT NOT NULL CHECK(permission_class IN ('L0_READ','L1_REVERSIBLE','L2_PERSONAL_WRITE','L3_EXTERNAL_WRITE','L4_DESTRUCTIVE')),
 requesting_context_json TEXT NOT NULL DEFAULT '{}', created_at REAL NOT NULL, expires_at REAL NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('PENDING','APPROVED','REJECTED','EXPIRED','EXECUTED','FAILED')),
 confirmed_at REAL, executed_at REAL, result_json TEXT NOT NULL DEFAULT '{}');
CREATE INDEX IF NOT EXISTS approvals_pending ON approvals(status,expires_at,created_at DESC);
CREATE TABLE IF NOT EXISTS visual_cards (
 id TEXT PRIMARY KEY, card_type TEXT NOT NULL CHECK(card_type IN ('DOCUMENT','RESEARCH','MEMORY','EMAIL','CALENDAR','BRIEFING','FOCUS','INVOICE','TELEGRAM','SYSTEM','APPROVAL')),
 title TEXT NOT NULL, payload_json TEXT NOT NULL, source_id TEXT NOT NULL DEFAULT '',
 created_at REAL NOT NULL, updated_at REAL NOT NULL, pinned INTEGER NOT NULL DEFAULT 0,
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','dismissed')));
CREATE INDEX IF NOT EXISTS visual_cards_latest ON visual_cards(status,pinned DESC,updated_at DESC);
PRAGMA user_version=5;
'''

class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version > 5: raise ValueError('Database schema is newer than this application')
            db.executescript(SCHEMA)
            columns={row['name'] for row in db.execute('PRAGMA table_info(memories)')}
            additions={
                'normalized':"TEXT NOT NULL DEFAULT ''",
                'source_type':"TEXT NOT NULL DEFAULT 'document'",
                'source_reference':"TEXT NOT NULL DEFAULT ''",
                'updated_at':'REAL NOT NULL DEFAULT 0',
                'importance':'REAL NOT NULL DEFAULT 0.5',
                'last_used_at':'REAL',
                'expires_at':'REAL',
                'status':"TEXT NOT NULL DEFAULT 'active'",
            }
            for name,declaration in additions.items():
                if name not in columns: db.execute(f'ALTER TABLE memories ADD COLUMN {name} {declaration}')
            db.execute("UPDATE memories SET normalized=lower(trim(content)) WHERE normalized=''")
            db.execute('UPDATE memories SET updated_at=created WHERE updated_at=0')
            db.execute('CREATE INDEX IF NOT EXISTS memory_active_category ON memories(status,category,updated_at DESC)')
            db.execute('CREATE INDEX IF NOT EXISTS memory_normalized ON memories(normalized)')
            db.execute('PRAGMA user_version=5')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA journal_mode=WAL')
        try:
            with db: yield db
        finally:
            db.close()

    def document(self, doc_id):
        with self.connect() as db:
            row = db.execute('''SELECT d.*, s.path, s.relative_path, s.modified, s.indexed
                FROM documents d JOIN sources s ON s.id=d.source_id
                WHERE d.id=? AND s.status='active' ''', (doc_id,)).fetchone()
            if not row: raise ValueError('Source is unavailable; reindex or select another note')
            return dict(row)

    def status(self):
        with self.connect() as db:
            counts = {t: db.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
                      for t in ['documents','chunks','entities','relationships','vectors']}
            counts['active_sources'] = db.execute("SELECT COUNT(*) FROM sources WHERE status='active'").fetchone()[0]
            counts['errors'] = [dict(r) for r in db.execute("SELECT relative_path,error FROM sources WHERE status='error'")]
            return counts
