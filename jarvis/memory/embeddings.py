"""Opt-in semantic vectors. No network at startup or during ordinary local indexing."""
import json
import math
import os

class Embeddings:
    def __init__(self, database, client=None):
        self.database = database
        self.client = client
        self.model = os.environ.get('JARVIS_EMBEDDING_MODEL', 'text-embedding-3-small')
        self.error = None

    @property
    def enabled(self):
        return self.client is not None or (os.environ.get('JARVIS_EMBEDDINGS') == 'openai' and bool(os.environ.get('OPENAI_API_KEY')))

    def embed(self, texts):
        if not self.enabled: return []
        if self.client is None:
            from openai import OpenAI
            self.client = OpenAI(timeout=30, max_retries=1)
        response = self.client.embeddings.create(model=self.model, input=texts)
        rows = sorted(response.data, key=lambda row: row.index)
        if len(rows) != len(texts): raise ValueError('Incomplete embeddings')
        vectors = [list(r.embedding) for r in rows]
        if not all(v and all(math.isfinite(x) for x in v) for v in vectors): raise ValueError('Invalid embeddings')
        if len({len(v) for v in vectors}) != 1: raise ValueError('Mismatched embeddings')
        return vectors

    def index(self):
        if not self.enabled: return {'mode':'keyword', 'embedded':0}
        with self.database.connect() as db:
            rows = db.execute('''SELECT c.id,c.text FROM chunks c JOIN documents d ON d.id=c.document_id
                JOIN sources s ON s.id=d.source_id LEFT JOIN vectors v ON v.chunk_id=c.id AND v.model=?
                WHERE s.status='active' AND v.chunk_id IS NULL''', (self.model,)).fetchall()
        count = 0
        for start in range(0,len(rows),32):
            batch = rows[start:start+32]
            vectors = self.embed([r['text'] for r in batch])
            with self.database.connect() as db:
                for row,vector in zip(batch,vectors):
                    # A concurrent scan may have removed a chunk; never resurrect it.
                    if db.execute('SELECT 1 FROM chunks WHERE id=?',(row['id'],)).fetchone():
                        db.execute('INSERT OR REPLACE INTO vectors VALUES (?,?,?)', (row['id'],self.model,json.dumps(vector)))
                        count += 1
        self.error = None
        return {'mode':'semantic', 'embedded':count}

def cosine(a,b):
    if len(a) != len(b): return 0.0
    norm = math.sqrt(sum(x*x for x in a)*sum(x*x for x in b))
    return sum(x*y for x,y in zip(a,b))/norm if norm else 0.0
