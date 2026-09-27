"""Source-supported document/topic graph; explicit provenance on every edge."""
class Graph:
    def __init__(self, database): self.database = database

    def snapshot(self, focus=None, limit=300):
        with self.database.connect() as db:
            docs = [dict(r) for r in db.execute('''SELECT d.id,d.title AS label,'DOCUMENT' AS kind,
                d.source_id,s.relative_path AS path FROM documents d JOIN sources s ON s.id=d.source_id
                WHERE s.status='active' ORDER BY d.title LIMIT ?''', (limit,))]
            edges = [dict(r) for r in db.execute('''SELECT r.* FROM relationships r
                JOIN sources s ON s.id=r.source_id WHERE s.status='active' ORDER BY r.id''')]
            if focus:
                related_docs = {focus}
                related_entities = {r['object'] for r in edges if r['subject'] == focus}
                related_docs.update(r['subject'] for r in edges if r['object'] == focus or r['object'] in related_entities)
                docs = [r for r in docs if r['id'] in related_docs]
            ids = {r['id'] for r in docs}
            edges = [r for r in edges if r['subject'] in ids]
            entity_ids = {r['object'] for r in edges}
            entities = [dict(r) for r in db.execute('SELECT id,name AS label,kind FROM entities') if r['id'] in entity_ids]
            return {'nodes': docs + entities, 'edges': edges, 'limit':limit,
                    'relation_policy':'Explicit headings, tags and wikilinks only; MENTIONS is not a factual claim.'}
