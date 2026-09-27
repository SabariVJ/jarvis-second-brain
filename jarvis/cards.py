"""Explicitly saved, bounded H.O.L.O visual cards; temporary cards stay in memory."""
import json
import re
import secrets
import time

from jarvis.security import redact


CARD_FIELDS={
    'DOCUMENT':{'summary','filename','source_ids','preview_url'},
    'RESEARCH':{'query','answer','sources','researched_at'},
    'MEMORY':{'memory_id','category','content','provenance'},
    'EMAIL':{'thread_id','subject','sender','date','summary'},
    'CALENDAR':{'event_id','summary','start','end'},
    'BRIEFING':{'generated_at','summary','calendar_count','email_count'},
    'FOCUS':{'goal','result','duration_seconds','distraction_count'},
    'INVOICE':{'document_id','summary','filename','preview_url'},
    'TELEGRAM':{'sender','summary','received_at'},
    'SYSTEM':{'status','summary','created_at'},
    'APPROVAL':{'approval_id','tool','permission_class','status','expires_at'},
}


class VisualCards:
    def __init__(self,database,clock=time.time):
        self.database=database;self.clock=clock;self.temporary={}

    @staticmethod
    def _clean(card_type,title,payload,source_id=''):
        if card_type not in CARD_FIELDS:raise ValueError('Card type is unsupported')
        if not isinstance(title,str) or not title.strip() or len(title)>180:raise ValueError('Card title is invalid')
        if not isinstance(payload,dict) or set(payload)-CARD_FIELDS[card_type]:raise ValueError('Card contains unsupported or sensitive fields')
        cleaned={}
        for key,value in payload.items():
            if key in {'sources','source_ids'}:
                if not isinstance(value,list) or len(value)>30:raise ValueError(f'{key} must be a short list')
                cleaned[key]=[VisualCards._clean_value(item,0) for item in value]
            else:cleaned[key]=VisualCards._clean_value(value,0)
        encoded=json.dumps(cleaned,ensure_ascii=False,separators=(',',':'),allow_nan=False)
        if len(encoded)>10000:raise ValueError('Card content exceeds 10 KB; keep a short summary')
        if not isinstance(source_id,str) or len(source_id)>160:raise ValueError('Card source ID is invalid')
        return title.strip(),cleaned,source_id

    @staticmethod
    def _clean_value(value,depth):
        if depth>4:raise ValueError('Card content is nested too deeply')
        if isinstance(value,str):return redact(value)[:4000]
        if isinstance(value,bool) or value is None or isinstance(value,int):return value
        if isinstance(value,float):
            if value!=value or abs(value)==float('inf'):raise ValueError('Card number must be finite')
            return value
        if isinstance(value,list):
            if len(value)>30:raise ValueError('Card list is too long')
            return [VisualCards._clean_value(item,depth+1) for item in value]
        if isinstance(value,dict):
            if len(value)>20:raise ValueError('Card object is too large')
            if any(re.search(r'(?i)(token|secret|password|credential|authorization|image_data|audio|raw_body)',str(k)) for k in value):
                raise ValueError('Sensitive fields cannot be saved to a card')
            return {str(k)[:80]:VisualCards._clean_value(v,depth+1) for k,v in value.items()}
        raise ValueError('Card content has an unsupported value')

    def save(self,card_type,title,payload,source_id=''):
        title,payload,source_id=self._clean(card_type,title,payload,source_id)
        now=float(self.clock());card_id='card_'+secrets.token_hex(12)
        encoded=json.dumps(payload,ensure_ascii=False,separators=(',',':'))
        with self.database.connect() as db:
            db.execute('INSERT INTO visual_cards(id,card_type,title,payload_json,source_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?)',
                (card_id,card_type,title,encoded,source_id,now,now))
            row=db.execute('SELECT * FROM visual_cards WHERE id=?',(card_id,)).fetchone()
        self.temporary.pop(source_id,None)
        return self._item(row)

    def add_temporary(self,card_type,title,payload,source_id=''):
        title,payload,source_id=self._clean(card_type,title,payload,source_id)
        card={'id':'temp_'+secrets.token_hex(8),'card_type':card_type,'title':title,'payload':payload,'source_id':source_id,
            'created_at':float(self.clock()),'updated_at':float(self.clock()),'pinned':False,'status':'temporary','persistence':'TEMPORARY'}
        self.temporary[card['id']]=card
        while len(self.temporary)>100:self.temporary.pop(next(iter(self.temporary)))
        return card

    @staticmethod
    def _item(row):return {'id':row['id'],'card_type':row['card_type'],'title':row['title'],'payload':json.loads(row['payload_json']),
        'source_id':row['source_id'],'created_at':row['created_at'],'updated_at':row['updated_at'],'pinned':bool(row['pinned']),
        'status':row['status'],'persistence':'PERSISTENT'}

    def list(self,include_dismissed=False):
        with self.database.connect() as db:
            query='SELECT * FROM visual_cards'+('' if include_dismissed else " WHERE status='active'")+ ' ORDER BY pinned DESC,updated_at DESC LIMIT 100'
            rows=db.execute(query).fetchall()
        return {'items':list(self.temporary.values())+[self._item(row) for row in rows]}

    def action(self,card_id,action):
        if card_id in self.temporary:
            if action in ('dismiss','remove'):
                self.temporary.pop(card_id,None);return {'id':card_id,'status':'dismissed' if action=='dismiss' else 'removed'}
            if action=='save':
                item=self.temporary[card_id];saved=self.save(item['card_type'],item['title'],item['payload'],item['source_id'])
                self.temporary.pop(card_id,None);return saved
            if action=='pin':raise ValueError('Save a temporary card before pinning it')
            raise ValueError('Card action is unsupported')
        if action not in ('pin','unpin','dismiss','save','remove','open'):
            raise ValueError('Card action is unsupported')
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM visual_cards WHERE id=?',(card_id,)).fetchone()
            if not row:raise ValueError('Card was not found')
            if action=='remove':db.execute('DELETE FROM visual_cards WHERE id=?',(card_id,))
            elif action=='dismiss':db.execute("UPDATE visual_cards SET status='dismissed',updated_at=? WHERE id=?",(float(self.clock()),card_id))
            elif action in ('pin','unpin'):db.execute('UPDATE visual_cards SET pinned=?,updated_at=? WHERE id=?',(int(action=='pin'),float(self.clock()),card_id))
            else:return self._item(row)
        return {'id':card_id,'status':'removed' if action=='remove' else action}
