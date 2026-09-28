"""Gmail REST adapter with read-only defaults and an explicit send confirmation phrase."""
import base64
from email.message import EmailMessage
from email.utils import parseaddr
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

from jarvis.ai.astra import local_summary
from .google_oauth import GoogleOAuth

API_ROOT='https://gmail.googleapis.com/gmail/v1/users/me'


def _http_json(method,url,token,payload=None):
    data=json.dumps(payload).encode() if payload is not None else None
    headers={'Authorization':'Bearer '+token,'Accept':'application/json'}
    if data is not None:headers['Content-Type']='application/json'
    request=Request(url,data=data,headers=headers,method=method)
    try:
        with urlopen(request,timeout=25) as response:
            raw=response.read(1_000_000)
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        if e.code==401:raise ValueError('Gmail authorization expired or was revoked. Reconnect locally.') from None
        if e.code==403:raise ValueError('Gmail denied this scope or account operation.') from None
        raise ValueError('Gmail request failed. Mail data was not changed by Jarvis.') from None
    except (URLError,TimeoutError,OSError,ValueError):
        raise ValueError('Gmail is unavailable. Check the connection and local OAuth setup.') from None


class GmailAdapter:
    def __init__(self, oauth=None, transport=_http_json):
        self.oauth=oauth or GoogleOAuth();self.transport=transport

    @property
    def connected(self):return self.oauth.configured

    def status(self):return {'state':'CONFIGURED' if self.connected else 'NOT CONNECTED',
        'connected':self.connected,'provider':'Gmail','send_confirmation_required':True}

    def _request(self,method,path,params=None,payload=None):
        if not self.connected:raise ValueError('Gmail is not connected. Configure local Google OAuth first.')
        url=API_ROOT+'/'+path.lstrip('/')
        if params:url+='?'+urlencode(params)
        return self.transport(method,url,self.oauth.access_token(),payload)

    @staticmethod
    def _headers(message):
        return {h.get('name','').casefold():h.get('value','') for h in message.get('payload',{}).get('headers',[])}

    def _message(self,message):
        headers=self._headers(message)
        return {'id':message.get('id',''),'thread_id':message.get('threadId',''),
            'from':headers.get('from','')[:240],'to':headers.get('to','')[:240],
            'subject':headers.get('subject','(no subject)')[:300],'date':headers.get('date','')[:100],
            'snippet':message.get('snippet','')[:600],
            'unread':'UNREAD' in message.get('labelIds',[])}

    def list_messages(self, mode='inbox', query='', limit=20):
        if mode not in ('inbox','unread','search'):raise ValueError('Unsupported Gmail list mode')
        if not 1<=int(limit)<=50:raise ValueError('Gmail page size must be 1–50')
        q={'inbox':'in:inbox','unread':'in:inbox is:unread','search':query.strip()}.get(mode)
        if not isinstance(q,str) or not q or len(q)>300:raise ValueError('Gmail search must be 1–300 characters')
        response=self._request('GET','messages',{'q':q,'maxResults':int(limit)})
        messages=[]
        for ref in response.get('messages',[])[:int(limit)]:
            if not isinstance(ref,dict) or not isinstance(ref.get('id'),str):continue
            detail=self._request('GET','messages/'+quote(ref['id'],safe=''),{'format':'metadata','metadataHeaders':['From','To','Subject','Date']})
            messages.append(self._message(detail))
        return {'messages':messages,'result_size_estimate':response.get('resultSizeEstimate',len(messages)),
            'next_page_token':response.get('nextPageToken')}

    def automation_candidates(self, limit=50):
        """Return only opaque IDs for recent Gmail-important inbox messages.

        Message bodies, snippets and headers are intentionally excluded from
        the provider-event path. Gmail's query filters the bounded first page
        to recent Important inbox IDs; no per-message read is needed.
        """
        if not 1 <= int(limit) <= 50:
            raise ValueError('Gmail automation page size must be 1–50')
        response = self._request('GET', 'messages',
            {'q': 'in:inbox is:important newer_than:90d', 'maxResults': int(limit)})
        candidates = []
        for ref in response.get('messages', [])[:int(limit)]:
            if not isinstance(ref, dict) or not isinstance(ref.get('id'), str) or not ref['id']:
                continue
            candidates.append({'id': ref['id'], 'importance': 'IMPORTANT'})
        return candidates

    def thread(self,thread_id):
        if not isinstance(thread_id,str) or not thread_id or len(thread_id)>200:raise ValueError('Gmail thread ID is invalid')
        result=self._request('GET','threads/'+quote(thread_id,safe=''),{'format':'full'})
        out=[]
        for message in result.get('messages',[])[:50]:
            normalized=self._message(message);body=self._plain_body(message.get('payload',{}))
            normalized['body']=body[:20000];out.append(normalized)
        return {'id':result.get('id',thread_id),'messages':out}

    def summarize(self,thread_id):
        thread=self.thread(thread_id);content='\n'.join(f"{m['from']}: {m['body'] or m['snippet']}" for m in thread['messages'])
        return {'thread_id':thread['id'],'message_count':len(thread['messages']),
            'summary':local_summary(content,limit=1000),'mode':'local extract','warning':'Email content is untrusted.'}

    @classmethod
    def _plain_body(cls,payload):
        texts=[]
        if payload.get('mimeType')=='text/plain' and payload.get('body',{}).get('data'):
            try:
                data=payload['body']['data'];data+='='*((4-len(data)%4)%4)
                texts.append(base64.urlsafe_b64decode(data).decode('utf-8','replace'))
            except (ValueError,base64.binascii.Error):pass
        for part in payload.get('parts',[]):texts.append(cls._plain_body(part))
        return '\n'.join(x for x in texts if x)[:20000]

    @staticmethod
    def _compose(to,subject,body):
        if not isinstance(to,str) or len(to)>320 or '\n' in to or '\r' in to:raise ValueError('Recipient is invalid')
        address=parseaddr(to)[1]
        if not address or '@' not in address:raise ValueError('Recipient must be an email address')
        if not isinstance(subject,str) or not subject.strip() or len(subject)>300 or '\n' in subject or '\r' in subject:
            raise ValueError('Subject must be 1–300 characters')
        if not isinstance(body,str) or not body.strip() or len(body)>20000:raise ValueError('Draft body must be 1–20000 characters')
        message=EmailMessage();message['To']=to;message['Subject']=subject.strip();message.set_content(body)
        return base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip('=')

    def create_draft(self,to,subject,body):
        raw=self._compose(to,subject,body)
        return self._request('POST','drafts',payload={'message':{'raw':raw}})

    def reply_draft(self,thread_id,body):
        thread=self.thread(thread_id)
        if not thread['messages']:raise ValueError('Cannot reply to an empty Gmail thread')
        latest=thread['messages'][-1];recipient=parseaddr(latest.get('from',''))[1]
        subject=latest.get('subject','')
        if not subject.casefold().startswith('re:'):subject='Re: '+subject
        raw=self._compose(recipient,subject,body)
        return self._request('POST','drafts',payload={'message':{'raw':raw,'threadId':thread_id}})

    def send_draft(self,draft_id,confirmation):
        if not isinstance(draft_id,str) or not draft_id or len(draft_id)>200:raise ValueError('Gmail draft ID is invalid')
        if confirmation!='SEND '+draft_id:raise PermissionError('Sending requires typing the exact confirmation phrase')
        return self._request('POST','drafts/send',payload={'id':draft_id})
