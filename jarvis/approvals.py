"""Local, expiring approval ledger bound to one validated tool and exact arguments."""
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
import time

from jarvis.tools import ToolError


@dataclass(frozen=True)
class ApprovalGrant:
    approval_id: str
    tool: str
    arguments_sha256: str


class ApprovalEngine:
    def __init__(self,database,registry,clock=time.time,ttl_seconds=300):
        self.database=database;self.registry=registry;self.clock=clock;self.ttl_seconds=max(30,min(int(ttl_seconds),1800))
        registry.authorizer=self.authorize

    @staticmethod
    def _canonical(args):
        return json.dumps(args,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)

    @staticmethod
    def _context(context):
        if not isinstance(context,dict):return {}
        current=context.get('current_context') if 'current_context' in context else context
        if not isinstance(current,dict):return {}
        return {key:current[key] for key in ('event','object_type','object_id','timestamp')
            if key in current and isinstance(current[key],(str,int,float))}

    @classmethod
    def _preview_value(cls,value,key=''):
        if re.search(r'(?i)(token|secret|password|credential|image_data_url|audio)',key):return '[hidden]'
        if re.search(r'(?i)^(body|content|address|snippet)$',key):
            return f'[hidden text · {len(value)} chars]' if isinstance(value,str) else '[hidden]'
        if isinstance(value,dict):return {k:cls._preview_value(v,k) for k,v in value.items()}
        if isinstance(value,list):return [cls._preview_value(item,key) for item in value[:30]]
        if isinstance(value,str):return value[:240]
        if value is None or isinstance(value,(int,float,bool)):return value
        return '[hidden]'

    def _item(self,row):
        args=json.loads(row['arguments_json'])
        return {'id':row['id'],'tool':row['tool'],'permission_class':row['permission_class'],
            'arguments_preview':self._preview_value(args),'requesting_context':json.loads(row['requesting_context_json']),
            'created_at':row['created_at'],'expires_at':row['expires_at'],'status':row['status'],
            'confirmed_at':row['confirmed_at'],'executed_at':row['executed_at'],
            'confirmation_phrase':'APPROVE '+row['id'] if row['status']=='PENDING' else None}

    def request(self,tool_name,args,context=None):
        tool,validated=self.registry.validate(tool_name,args)
        if tool.permission_class=='L0_READ':raise ValueError('Read-only tools do not need an approval')
        if not tool.available:raise ValueError('This tool is not available in the current runtime')
        encoded=self._canonical(validated)
        if len(encoded)>60000:raise ValueError('Approval arguments exceed the supported size')
        now=float(self.clock());approval_id='approval_'+secrets.token_hex(12)
        digest=hashlib.sha256(encoded.encode('utf-8')).hexdigest()
        requesting=self._context(context)
        with self.database.connect() as db:
            db.execute('''INSERT INTO approvals(id,tool,arguments_json,arguments_sha256,permission_class,
                requesting_context_json,created_at,expires_at,status) VALUES(?,?,?,?,?,?,?,?,?)''',
                (approval_id,tool_name,encoded,digest,tool.permission_class,
                 json.dumps(requesting,ensure_ascii=False,separators=(',',':')),now,now+self.ttl_seconds,'PENDING'))
            row=db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
        return self._item(row)

    def list_pending(self,limit=50):
        now=float(self.clock())
        with self.database.connect() as db:
            db.execute("UPDATE approvals SET status='EXPIRED' WHERE status='PENDING' AND expires_at<=?",(now,))
            rows=db.execute("SELECT * FROM approvals WHERE status='PENDING' ORDER BY created_at DESC LIMIT ?",(max(1,min(int(limit),100)),)).fetchall()
        return {'items':[self._item(row) for row in rows]}

    def get(self,approval_id):
        if not isinstance(approval_id,str) or not re.fullmatch(r'approval_[a-f0-9]{24}',approval_id):raise ValueError('Approval ID is invalid')
        with self.database.connect() as db:row=db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
        if not row:raise ValueError('Approval was not found')
        return self._item(row)

    def reject(self,approval_id):
        now=float(self.clock())
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
            if not row:raise ValueError('Approval was not found')
            if row['status']!='PENDING':return self._item(row)
            status='EXPIRED' if row['expires_at']<=now else 'REJECTED'
            db.execute('UPDATE approvals SET status=? WHERE id=? AND status=\'PENDING\'',(status,approval_id))
            row=db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
        return self._item(row)

    def confirm(self,approval_id,confirmation):
        now=float(self.clock())
        expired=False
        with self.database.connect() as db:
            row=db.execute('SELECT * FROM approvals WHERE id=?',(approval_id,)).fetchone()
            if not row:raise ValueError('Approval was not found')
            if row['status']!='PENDING':raise ValueError('Approval is no longer pending')
            if row['expires_at']<=now:
                db.execute("UPDATE approvals SET status='EXPIRED' WHERE id=?",(approval_id,))
                expired=True
            else:
                expected='APPROVE '+approval_id
                if not isinstance(confirmation,str) or not hmac.compare_digest(confirmation,expected):
                    raise ValueError('Exact local approval phrase is required')
                changed=db.execute("UPDATE approvals SET status='APPROVED',confirmed_at=? WHERE id=? AND status='PENDING' AND expires_at>?",(now,approval_id,now)).rowcount
                if changed!=1:raise ValueError('Approval is no longer pending')
                arguments=json.loads(row['arguments_json']);digest=row['arguments_sha256'];tool=row['tool']
        if expired:raise ValueError('Approval expired; request a new one')
        return self._execute_approved(approval_id,tool,arguments,digest)

    def execute_explicit_user_command(self,tool_name,args,context=None):
        """The user's imperative memory command is its own explicit consent."""
        request=self.request(tool_name,args,context)
        now=float(self.clock())
        with self.database.connect() as db:
            db.execute("UPDATE approvals SET status='APPROVED',confirmed_at=? WHERE id=? AND status='PENDING'",(now,request['id']))
        return self._execute_approved(request['id'],tool_name,args,hashlib.sha256(self._canonical(args).encode('utf-8')).hexdigest())

    def _execute_approved(self,approval_id,tool_name,args,digest):
        grant=ApprovalGrant(approval_id,tool_name,digest)
        try:result=self.registry.execute(tool_name,args,authorization=grant)
        except Exception as error:
            result=getattr(error,'result',{'ok':False,'tool':tool_name,'result':None,
                'error':{'code':'EXECUTION_FAILED','message':'Approved action failed'},'verification':'NOT_RUN'})
        finished=float(self.clock());status='EXECUTED' if result.get('ok') else 'FAILED'
        try:encoded=json.dumps(result,ensure_ascii=False,separators=(',',':'),default=str)
        except (TypeError,ValueError):encoded='{}'
        if len(encoded)>100000:encoded=json.dumps({'ok':result.get('ok',False),'truncated':True})
        with self.database.connect() as db:
            db.execute('UPDATE approvals SET status=?,executed_at=?,result_json=? WHERE id=? AND status=\'APPROVED\'',
                (status,finished,encoded,approval_id))
        return {'approval':self.get(approval_id),'tool_result':result}

    def authorize(self,tool,args,authorization):
        if not isinstance(authorization,ApprovalGrant):return False
        if authorization.tool!=tool.name:return False
        try:digest=hashlib.sha256(self._canonical(args).encode('utf-8')).hexdigest()
        except (TypeError,ValueError):return False
        if not hmac.compare_digest(digest,authorization.arguments_sha256):return False
        with self.database.connect() as db:
            row=db.execute('''SELECT 1 FROM approvals WHERE id=? AND tool=? AND arguments_sha256=?
                AND status='APPROVED' AND expires_at>?''',(authorization.approval_id,tool.name,digest,float(self.clock()))).fetchone()
        return bool(row)
