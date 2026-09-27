"""Hybrid rank fusion: FTS, filename fuzzy matching, optional vectors, weak recency."""
import json
import re
import time
from difflib import SequenceMatcher
from .embeddings import cosine

STOP = set('jarvis find my me the a an where did we talk about show everything related to notes note file please is it stored summarize this open and or not'.split())
def terms(query):
    return [t for t in re.findall(r'\w+', query.casefold()) if t not in STOP][:32]

class Retrieval:
    def __init__(self, database, embeddings):
        self.database, self.embeddings = database, embeddings

    def search(self, query, limit=8):
        if not isinstance(query,str) or len(query) > 2000: raise ValueError('Search must be at most 2000 characters')
        tokens = terms(query)
        if not tokens: return {'results':[], 'mode':'keyword', 'warning':None}
        warning, query_vector = None, []
        if self.embeddings.enabled:
            try: query_vector = self.embeddings.embed([query])[0]
            except Exception: warning = 'Semantic service unavailable; using local search'
        with self.database.connect() as db:
            rows = db.execute('''SELECT c.*,d.title,d.fingerprint,d.source_id,s.path,s.relative_path,s.modified,
                v.embedding FROM chunks c JOIN documents d ON d.id=c.document_id
                JOIN sources s ON s.id=d.source_id LEFT JOIN vectors v ON v.chunk_id=c.id AND v.model=?
                WHERE s.status='active' ''', (self.embeddings.model,)).fetchall()
            fts = {r['id']:i for i,r in enumerate(db.execute('''SELECT id FROM chunk_fts
                WHERE chunk_fts MATCH ? ORDER BY bm25(chunk_fts) LIMIT 200''',
                (' OR '.join('"'+t+'"' for t in tokens),)))}
            candidates = []
            for row in rows:
                meta = (row['title']+' '+row['relative_path']).casefold()
                metadata = sum(t in meta for t in tokens)/len(tokens)
                fuzzy = max((SequenceMatcher(None,t,w).ratio() for t in tokens for w in re.findall(r'\w+',meta)), default=0)
                semantic = max(0,cosine(query_vector,json.loads(row['embedding']))) if query_vector and row['embedding'] else 0
                lexical = 1/(1+fts[row['id']]*.15) if row['id'] in fts else 0
                if not lexical and not metadata and fuzzy < .78 and semantic < .25: continue
                recency = 1/(1+max(0,time.time()-row['modified'])/86400/90)
                score = .45*lexical + .45*semantic + .20*metadata + .08*(fuzzy if fuzzy>=.78 else 0) + .02*recency
                item = dict(row); item.pop('embedding')
                item.update(score=round(score,5), semantic_score=round(semantic,5), node_id=row['document_id'])
                candidates.append(item)
        candidates.sort(key=lambda r:r['score'], reverse=True)
        # Content duplicates share a result, but preserve alternate source paths.
        results, seen = [], {}
        for item in candidates:
            key = item['fingerprint']
            if key in seen:
                previous = seen[key]
                if item['path'] != previous['path'] and item['path'] not in previous['duplicate_paths']:
                    previous['duplicate_paths'].append(item['path'])
                continue
            item['duplicate_paths'] = []; seen[key] = item; results.append(item)
        return {'results':results[:max(1,min(20,limit))],
                'mode':'hybrid' if query_vector and any(r['embedding'] for r in rows) else 'keyword', 'warning':warning}
