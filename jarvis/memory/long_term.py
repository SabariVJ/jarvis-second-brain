"""Intentional, source-backed personal memories; external data cannot auto-save."""
from datetime import datetime, timezone
import hashlib
import math
import re
import time
import unicodedata
import uuid


CATEGORIES={'PROFILE','PREFERENCE','PROJECT','PERSON','DECISION','WORKFLOW','EPISODE','TASK'}
SOURCE_TYPES={'user_explicit','user_chat','user_update','telegram_explicit'}
_CREDENTIALS=re.compile(
    r'(?i)(?:\b(?:password|passphrase|api[ _-]?key|oauth(?:\s+refresh)? token|access token|refresh token|client secret|bot token)\b\s*(?:is|=|:|：)\s*\S+|'
    r'\bsk-[a-z0-9_-]{16,}|\bgh[pousr]_[a-z0-9]{24,}|\bxox[baprs]-[a-z0-9-]{16,}|\b\d{6,}:[a-z0-9_-]{20,}|\bya29\.[a-z0-9._-]{16,})')
_SIGNIFICANT=(
    ('PREFERENCE',re.compile(r'^(?:i prefer\b|my preferred\b|i like to\b)')),
    ('PROFILE',re.compile(r'^(?:my name is\b|call me\b|i go by\b|i am based in\b|i live in\b)')),
    ('PROJECT',re.compile(r'^(?:my project\b|i work on\b|i am working on\b|we are building\b)')),
    ('DECISION',re.compile(r'^(?:we decided\b|i decided\b|our decision is\b)')),
    ('WORKFLOW',re.compile(r'^(?:my workflow\b|when i\b.*\b(always|usually|first|then)\b)')),
    ('TASK',re.compile(r'^(?:my goal is\b|i need to (?:finish|complete|submit)\b.*\b(?:by|before|task)\b)')),
)


def normalize(content):
    value=unicodedata.normalize('NFKC',content).casefold()
    value=re.sub(r'[^\w\s]',' ',value,flags=re.UNICODE)
    return ' '.join(value.split())


def infer_category(content):
    text=content.strip().casefold()
    for category,pattern in _SIGNIFICANT:
        if pattern.search(text):return category
    if re.search(r'\b(?:my manager|my colleague|my partner|my wife|my husband|my teammate)\b',text):return 'PERSON'
    return 'EPISODE'


class LongTermMemory:
    def __init__(self,database,clock=time.time):self.database=database;self.clock=clock

    @staticmethod
    def _validate_content(content):
        if not isinstance(content,str) or not 2<=len(content.strip())<=2000:
            raise ValueError('Memory content must contain 2–2000 characters')
        content=' '.join(content.strip().split())
        if _CREDENTIALS.search(content):raise ValueError('Credentials and secrets cannot be stored as memories')
        return content

    @staticmethod
    def _validate_category(category,content):
        category=infer_category(content) if category is None else category
        if not isinstance(category,str):raise ValueError('Unsupported memory category')
        category=category.strip().upper()
        if category not in CATEGORIES:raise ValueError('Unsupported memory category')
        return category

    def _item(self,row):
        if not row:return None
        row=dict(row)
        return {'id':row['id'],'category':row['category'],'content':row['content'],
            'created_at':datetime.fromtimestamp(row['created'],timezone.utc).isoformat(),
            'updated_at':datetime.fromtimestamp(row['updated_at'],timezone.utc).isoformat(),
            'confidence':row['confidence'],'importance':row['importance'],
            'last_used_at':datetime.fromtimestamp(row['last_used_at'],timezone.utc).isoformat() if row['last_used_at'] else None,
            'expires_at':datetime.fromtimestamp(row['expires_at'],timezone.utc).isoformat() if row['expires_at'] else None,
            'status':row['status'],'source':{'id':row['source_id'],'type':row['source_type'],
                'reference':row['source_reference'],'label':row.get('relative_path',f"Source record {row['source_id']}")}}

    @staticmethod
    def _source_row(db,memory_id,content,now,source_type,source_reference):
        digest=hashlib.sha256(content.encode('utf-8')).hexdigest()
        db.execute('''INSERT INTO sources(id,root,path,relative_path,fingerprint,modified,indexed,status,error,media_type)
            VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET
            relative_path=excluded.relative_path,fingerprint=excluded.fingerprint,modified=excluded.modified,
            indexed=excluded.indexed,status='active',error=NULL''',
            (memory_id,'jarvis-memory',f'jarvis-memory://{memory_id}',f'Long-term memory · {source_type} · {memory_id[-8:]}',
             digest,now,now,'active',None,'application/x-jarvis-memory'))

    def remember(self,content,category=None,source_type='user_explicit',source_reference='User explicitly asked Jarvis to remember this.',
        confidence=.95,importance=.8,expires_at=None):
        content=self._validate_content(content)
        if not isinstance(source_type,str) or source_type not in SOURCE_TYPES:raise ValueError('Memory provenance must be a user-authored source')
        if not isinstance(source_reference,str) or not source_reference.strip() or len(source_reference)>240:
            raise ValueError('A concise provenance reference is required')
        if not isinstance(confidence,(int,float)) or not math.isfinite(confidence) or not 0<=confidence<=1:raise ValueError('Confidence must be between 0 and 1')
        if not isinstance(importance,(int,float)) or not math.isfinite(importance) or not 0<=importance<=1:raise ValueError('Importance must be between 0 and 1')
        if expires_at is not None and (not isinstance(expires_at,(int,float)) or not math.isfinite(expires_at) or expires_at<=self.clock()):
            raise ValueError('Expiration must be a future timestamp')
        category=self._validate_category(category,content);normalized=normalize(content);now=self.clock();memory_id='mem_'+uuid.uuid4().hex
        with self.database.connect() as db:
            duplicate=db.execute('''SELECT * FROM memories WHERE normalized=? AND status='active'
                AND (expires_at IS NULL OR expires_at>?) ORDER BY updated_at DESC LIMIT 1''',(normalized,now)).fetchone()
            if duplicate:return {**self._item(duplicate),'duplicate':True}
            self._source_row(db,memory_id,content,now,source_type,source_reference.strip())
            db.execute('''INSERT INTO memories(id,category,content,source_id,created,confidence,normalized,
                source_type,source_reference,updated_at,importance,last_used_at,expires_at,status)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'active')''',
                (memory_id,category,content,memory_id,now,float(confidence),normalized,source_type,
                 source_reference.strip(),now,float(importance),None,expires_at))
            row=db.execute('SELECT * FROM memories WHERE id=?',(memory_id,)).fetchone()
            return {**self._item(row),'duplicate':False}

    def capture_significant(self,user_text):
        if not isinstance(user_text,str) or len(user_text)>2000:return None
        text=' '.join(user_text.strip().split())
        if text.endswith('?') or _CREDENTIALS.search(text):return None
        lower=text.casefold()
        if lower.startswith(('remember ','what do you remember','forget ','update what you remember','correct that memory','don\'t remember','do not remember')):return None
        category=next((cat for cat,pattern in _SIGNIFICANT if pattern.search(lower)),None)
        if category is None and re.search(r'\b(?:my manager|my colleague|my partner|my wife|my husband|my teammate)\b',lower):category='PERSON'
        if category is None:return None
        return self.remember(text,category,'user_chat','User-authored statement matched the conservative '+category.lower()+' rule.',.78,.65)

    def search(self,query='',category=None,limit=20):
        if not isinstance(query,str) or len(query)>300:raise ValueError('Memory search must be at most 300 characters')
        if category is not None:
            if not isinstance(category,str):raise ValueError('Unsupported memory category')
            category=category.strip().upper()
            if category not in CATEGORIES:raise ValueError('Unsupported memory category')
        if not isinstance(limit,int) or not 1<=limit<=50:raise ValueError('Memory page size must be 1–50')
        terms=normalize(query).split();now=self.clock()
        # An empty query is useful for the explicit memory manager's recent-items view.
        clauses=["status='active'",'(expires_at IS NULL OR expires_at>?)'];params=[now]
        if category:clauses.append('category=?');params.append(category)
        for term in terms[:15]:clauses.append('normalized LIKE ? ESCAPE \'\\\'');params.append('%'+term.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%')
        params.append(limit)
        with self.database.connect() as db:
            rows=db.execute('SELECT * FROM memories WHERE '+' AND '.join(clauses)+' ORDER BY importance DESC,updated_at DESC LIMIT ?',params).fetchall()
            if rows:
                db.executemany('UPDATE memories SET last_used_at=? WHERE id=?',[(now,row['id']) for row in rows])
            return [self._item({**dict(row),'last_used_at':now}) for row in rows]

    def inspect(self,memory_id):
        if not isinstance(memory_id,str) or len(memory_id)>80:raise ValueError('Memory ID is invalid')
        now=self.clock()
        with self.database.connect() as db:
            row=db.execute("SELECT * FROM memories WHERE id=? AND status='active' AND (expires_at IS NULL OR expires_at>?)",(memory_id,now)).fetchone()
            if not row:raise ValueError('Memory not found or expired')
            db.execute('UPDATE memories SET last_used_at=? WHERE id=?',(now,memory_id))
            return self._item({**dict(row),'last_used_at':now})

    def update(self,memory_id,content,category=None,source_reference='User explicitly corrected this memory.'):
        content=self._validate_content(content);normalized=normalize(content);now=self.clock()
        if not isinstance(memory_id,str) or len(memory_id)>80:raise ValueError('Memory ID is invalid')
        if not isinstance(source_reference,str) or not source_reference.strip() or len(source_reference)>240:
            raise ValueError('A concise provenance reference is required')
        with self.database.connect() as db:
            row=db.execute("SELECT * FROM memories WHERE id=? AND status='active'",(memory_id,)).fetchone()
            if not row:raise ValueError('Memory not found')
            category=self._validate_category(category or row['category'],content)
            duplicate=db.execute("SELECT id FROM memories WHERE normalized=? AND status='active' AND id<>?",(normalized,memory_id)).fetchone()
            if duplicate:raise ValueError('An equivalent memory already exists')
            self._source_row(db,memory_id,content,now,'user_update',source_reference)
            db.execute('''UPDATE memories SET category=?,content=?,normalized=?,source_type='user_update',
                source_reference=?,updated_at=?,confidence=.98,importance=max(importance,.8),expires_at=NULL WHERE id=?''',
                (category,content,normalized,source_reference,now,memory_id))
            row=db.execute('SELECT * FROM memories WHERE id=?',(memory_id,)).fetchone()
            return self._item(row)

    def forget(self,memory_id):
        if not isinstance(memory_id,str) or len(memory_id)>80:raise ValueError('Memory ID is invalid')
        now=self.clock()
        with self.database.connect() as db:
            row=db.execute("SELECT id,source_id FROM memories WHERE id=? AND status='active'",(memory_id,)).fetchone()
            if not row:raise ValueError('Memory not found')
            db.execute('DELETE FROM memories WHERE id=?',(memory_id,))
            db.execute('''UPDATE sources SET status='deleted',relative_path='Forgotten long-term memory',
                fingerprint=?,modified=?,indexed=?,error=NULL WHERE id=?''',
                (hashlib.sha256(b'').hexdigest(),now,now,row['source_id']))
            return {'forgotten':True,'id':memory_id}

    def capture_allowed(self,content,source_type):
        """Explicit save for an authenticated user; external context is never accepted."""
        if source_type not in ('user_explicit','telegram_explicit'):
            raise ValueError('Only explicit user requests can create persistent memories')
        return self.remember(content,source_type=source_type,
            source_reference='User explicitly requested memory via '+('authorized Telegram' if source_type=='telegram_explicit' else 'local Jarvis')+'.')
