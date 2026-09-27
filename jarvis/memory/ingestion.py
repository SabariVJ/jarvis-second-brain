"""Read-only folder ingestion. Tombstones preserve provenance, never stale answers."""
from pathlib import Path
from threading import Lock
import hashlib
import re
import time
from .database import stable_id

MAX_BYTES = 20 * 1024 * 1024
MAX_TEXT = 2_000_000

def text_reader(path):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        return handle.read()

def pdf_reader(path):
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ValueError('PDF requires pypdf; install requirements.txt') from None
    reader = PdfReader(path)
    if reader.is_encrypted: raise ValueError('Encrypted PDF needs a decrypted local copy')
    if len(reader.pages) > 500: raise ValueError('PDF exceeds 500 page limit')
    parts = [f'\n[Page {i+1}]\n{p.extract_text() or ""}' for i, p in enumerate(reader.pages)]
    if not any(re.search(r'\w', p.split(']', 1)[-1]) for p in parts):
        raise ValueError('No extractable PDF text; OCR is not enabled')
    return '\n'.join(parts)

READERS = {'.md': text_reader, '.txt': text_reader, '.pdf': pdf_reader}

def chunks(text, size=1400, overlap=180):
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        if end < len(text):
            for sep in ['\n\n', '\n', '. ', ' ']:
                cut = text.rfind(sep, start + size // 2, end)
                if cut >= 0:
                    end = cut + len(sep); break
        yield start, end, text[start:end]
        if end == len(text): break
        start = max(start + 1, end - overlap)

def entities_for(text):
    # Only explicit headings, hashtags and wikilinks. Never invent semantic relations.
    matches = []
    for match in re.finditer(r'^#{1,6}\s+(.+)$|\[\[([^\]|]+)(?:\|[^\]]+)?\]\]|(?<!\w)#([\w-]+)', text, re.M):
        name = next(g for g in match.groups() if g).strip()
        if len(name) <= 100:
            matches.append((name, match.group(0)))
    return matches[:100]

class Ingestor:
    def __init__(self, database):
        self.database = database
        self.lock = Lock()

    def scan(self, root):
        root = Path(root).resolve()
        if not root.is_dir(): raise ValueError('Notes folder unavailable; existing index preserved')
        if not self.lock.acquire(False): raise ValueError('Indexing is already running')
        try:
            return self._scan(root)
        finally:
            self.lock.release()

    def _scan(self, root):
        seen, result = set(), {'indexed':0, 'unchanged':0, 'deleted':0, 'errors':[]}
        # os.walk with onerror is deliberate: never mistake unreadable subtrees for deletions.
        import os
        paths = []
        walk_errors = []
        for folder, dirs, files in os.walk(root, followlinks=False, onerror=walk_errors.append):
            dirs[:] = [d for d in dirs if not d.startswith('.') and not Path(folder,d).is_symlink()
                       and Path(folder,d).resolve().is_relative_to(root)
                       and not (Path(folder,d).stat().st_file_attributes & 1024 if os.name == 'nt' else False)]
            paths.extend(Path(folder,n) for n in sorted(files) if not n.startswith('.') and Path(n).suffix.lower() in READERS)
        if walk_errors: raise ValueError('Folder scan incomplete; index preserved')
        with self.database.connect() as db:
            for path in sorted(paths):
                if path.is_symlink() or not path.resolve().is_relative_to(root): continue
                path = path.resolve(); key = str(path); seen.add(key)
                sid, did = stable_id('source', key), stable_id('doc', key)
                old = db.execute('SELECT * FROM sources WHERE id=?', (sid,)).fetchone()
                fingerprint, modified = '', 0
                try:
                    stat = path.stat(); modified = stat.st_mtime
                    if stat.st_size > MAX_BYTES: raise ValueError('File exceeds 20 MiB limit')
                    raw = path.read_bytes(); fingerprint = hashlib.sha256(raw).hexdigest()
                    if old and old['fingerprint'] == fingerprint and old['status'] == 'active':
                        result['unchanged'] += 1; continue
                    body = READERS[path.suffix.lower()](path)
                    if len(body) > MAX_TEXT: raise ValueError('Extracted text exceeds limit')
                    if hashlib.sha256(path.read_bytes()).hexdigest() != fingerprint:
                        raise ValueError('File changed during indexing; retry')
                    title = next((l.lstrip('# ').strip() for l in body.splitlines() if l.strip()), path.stem)[:160]
                except Exception as exc:
                    error = str(exc) if isinstance(exc, ValueError) else 'File could not be read'
                    result['errors'].append({'path':str(path.relative_to(root)), 'error':error})
                    self._source(db, sid, root, path, fingerprint, modified, 'error', error)
                    continue
                self._source(db, sid, root, path, fingerprint, modified, 'active', None)
                db.execute('DELETE FROM chunk_fts WHERE id IN (SELECT id FROM chunks WHERE document_id=?)', (did,))
                db.execute('DELETE FROM chunks WHERE document_id=?', (did,))
                db.execute('''INSERT INTO documents VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE
                    SET title=excluded.title, body=excluded.body, fingerprint=excluded.fingerprint''', (did,sid,title,body,fingerprint))
                for ordinal,(start,end,text) in enumerate(chunks(body)):
                    cid = stable_id('chunk', f'{did}:{ordinal}:{fingerprint}')
                    db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)', (cid,did,ordinal,text,start,end))
                    db.execute('INSERT INTO chunk_fts VALUES (?,?,?,?)', (cid,text,title,str(path.relative_to(root))))
                db.execute('DELETE FROM relationships WHERE source_id=?', (sid,))
                for name,evidence in entities_for(body):
                    eid = stable_id('entity', name.casefold())
                    db.execute('INSERT OR IGNORE INTO entities VALUES (?,?,?)', (eid,name,'TOPIC'))
                    rid = stable_id('relation', did + eid + evidence)
                    db.execute('INSERT OR IGNORE INTO relationships VALUES (?,?,?,?,?,?,?)',
                               (rid,did,'MENTIONS',eid,sid,evidence,1.0))
                result['indexed'] += 1
            for row in db.execute("SELECT id,path FROM sources WHERE root=? AND status != 'deleted'", (str(root),)).fetchall():
                if row['path'] not in seen:
                    db.execute("UPDATE sources SET status='deleted' WHERE id=?", (row['id'],))
                    result['deleted'] += 1
            # Switching the configured folder revokes visibility of old roots.
            db.execute("UPDATE sources SET status='deleted' WHERE root != ? AND root != 'research://kept'", (str(root),))
        return result

    def save_research(self, card):
        """Explicitly promote a verified transient card into local, untrusted memory."""
        import json
        from datetime import datetime, timezone
        root = 'research://kept'
        path = root + '/' + card['id']
        sid, did = stable_id('source', path), stable_id('doc', path)
        stamp = datetime.fromtimestamp(card['researched_at'], timezone.utc).isoformat()
        sources = '\n'.join(f"- {s['title']} — {s['url']}\n  Cited answer excerpt: {s['snippet']}" for s in card['sources'])
        body = f"# Saved research: {card['query']}\n\nCaptured: {stamp}\nWeb-derived material is untrusted.\n\n{card['answer']}\n\nSources:\n{sources}"
        fingerprint = hashlib.sha256(body.encode('utf-8')).hexdigest()
        title = ('Research: ' + card['query'])[:160]
        with self.database.connect() as db:
            old = db.execute('SELECT id FROM documents WHERE id=?',(did,)).fetchone()
            if old:
                return did
            db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (sid,root,path,title,fingerprint,card['researched_at'],time.time(),'active',None,'text/x-jarvis-research'))
            db.execute('INSERT INTO documents VALUES (?,?,?,?,?)',(did,sid,title,body,fingerprint))
            for ordinal,(start,end,text) in enumerate(chunks(body)):
                cid = stable_id('chunk', f'{did}:{ordinal}:{fingerprint}')
                db.execute('INSERT INTO chunks VALUES (?,?,?,?,?,?)',(cid,did,ordinal,text,start,end))
                db.execute('INSERT INTO chunk_fts VALUES (?,?,?,?)',(cid,text,title,title))
        return did

    def _source(self, db, sid, root, path, fingerprint, modified, status, error):
        db.execute('''INSERT INTO sources VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            fingerprint=excluded.fingerprint, modified=excluded.modified, indexed=excluded.indexed,
            status=excluded.status, error=excluded.error''',
            (sid,str(root),str(path),str(path.relative_to(root)),fingerprint,modified,time.time(),status,error,path.suffix.lower()))
