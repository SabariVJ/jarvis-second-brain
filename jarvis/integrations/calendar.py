"""Google Calendar adapter. Mutations require exact server-checked confirmation."""
from datetime import datetime, timedelta
from urllib.parse import urlencode, quote
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .google_oauth import GoogleOAuth

API_ROOT='https://www.googleapis.com/calendar/v3'


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
        if e.code==401:raise ValueError('Google Calendar authorization expired or was revoked.') from None
        if e.code==403:raise ValueError('Google Calendar denied the requested permission.') from None
        raise ValueError('Google Calendar request failed. The event was not confirmed.') from None
    except (URLError,TimeoutError,OSError,ValueError):
        raise ValueError('Google Calendar is unavailable. Check local OAuth setup and connection.') from None


def _instant(value, label):
    if not isinstance(value,str) or len(value)>64:raise ValueError(f'{label} must be an ISO date/time')
    try:parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:raise ValueError(f'{label} must be an ISO date/time') from None
    if parsed.tzinfo is None:raise ValueError(f'{label} must include a timezone')
    return parsed.isoformat()


class CalendarAdapter:
    def __init__(self,oauth=None,transport=_http_json,now=None):
        self.oauth=oauth or GoogleOAuth();self.transport=transport;self.now=now or (lambda:datetime.now().astimezone())

    @property
    def connected(self):return self.oauth.configured

    def status(self):return {'state':'CONFIGURED' if self.connected else 'NOT CONNECTED',
        'connected':self.connected,'provider':'Google Calendar','write_confirmation_required':True}

    def _request(self,method,path,params=None,payload=None):
        if not self.connected:raise ValueError('Google Calendar is not connected. Configure local Google OAuth first.')
        url=API_ROOT+'/'+path.lstrip('/')
        if params:url+='?'+urlencode(params)
        return self.transport(method,url,self.oauth.access_token(),payload)

    @staticmethod
    def _normalize(event):
        start=event.get('start',{});end=event.get('end',{})
        return {'id':event.get('id',''),'summary':event.get('summary','(no title)')[:300],
            'start':start.get('dateTime',start.get('date','')),'end':end.get('dateTime',end.get('date','')),
            'location':event.get('location','')[:300],'status':event.get('status','confirmed'),
            'html_link':event.get('htmlLink','')[:1000]}

    def events(self,start,end,query='',limit=100):
        begin=_instant(start,'Start');finish=_instant(end,'End')
        if datetime.fromisoformat(finish)<=datetime.fromisoformat(begin):raise ValueError('End must be after start')
        if not isinstance(query,str) or len(query)>300:raise ValueError('Event search must be 0–300 characters')
        if not 1<=int(limit)<=250:raise ValueError('Calendar page size must be 1–250')
        params={'timeMin':begin,'timeMax':finish,'singleEvents':'true','orderBy':'startTime','maxResults':int(limit)}
        if query.strip():params['q']=query.strip()
        result=self._request('GET','calendars/primary/events',params)
        return {'items':[self._normalize(x) for x in result.get('items',[])[:int(limit)] if isinstance(x,dict)],
            'next_page_token':result.get('nextPageToken')}

    def today(self):
        now=self.now();start=now.replace(hour=0,minute=0,second=0,microsecond=0)
        return self.events(start.isoformat(),(start+timedelta(days=1)).isoformat())

    def tomorrow(self):
        start=self.now().replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
        return self.events(start.isoformat(),(start+timedelta(days=1)).isoformat())

    def availability(self,start,end):
        begin=_instant(start,'Start');finish=_instant(end,'End')
        if datetime.fromisoformat(finish)<=datetime.fromisoformat(begin):raise ValueError('End must be after start')
        result=self._request('POST','freeBusy',payload={'timeMin':begin,'timeMax':finish,'items':[{'id':'primary'}]})
        calendar=result.get('calendars',{}).get('primary',{})
        return {'time_min':begin,'time_max':finish,'busy':calendar.get('busy',[]),'errors':calendar.get('errors',[])}

    def create(self,summary,start,end,confirmation,description=''):
        title=self._text(summary,'Event title',300);begin=_instant(start,'Start');finish=_instant(end,'End')
        if datetime.fromisoformat(finish)<=datetime.fromisoformat(begin):raise ValueError('End must be after start')
        if not isinstance(description,str) or len(description)>5000:raise ValueError('Description must be 0–5000 characters')
        if confirmation!='CREATE '+title:raise PermissionError('Creating an event requires the exact confirmation phrase')
        event=self._request('POST','calendars/primary/events',payload={'summary':title,'description':description,
            'start':{'dateTime':begin},'end':{'dateTime':finish}})
        if not isinstance(event,dict) or not event.get('id'):raise ValueError('Calendar did not confirm event creation')
        return {'confirmed':True,**self._normalize(event)}

    def reschedule(self,event_id,start,end,confirmation):
        identifier=self._id(event_id);begin=_instant(start,'Start');finish=_instant(end,'End')
        if datetime.fromisoformat(finish)<=datetime.fromisoformat(begin):raise ValueError('End must be after start')
        if confirmation!='RESCHEDULE '+identifier:raise PermissionError('Rescheduling requires the exact confirmation phrase')
        event=self._request('PATCH','calendars/primary/events/'+quote(identifier,safe=''),payload={
            'start':{'dateTime':begin},'end':{'dateTime':finish}})
        if not isinstance(event,dict) or event.get('id')!=identifier:raise ValueError('Calendar did not confirm event rescheduling')
        return {'confirmed':True,**self._normalize(event)}

    def cancel(self,event_id,confirmation):
        identifier=self._id(event_id)
        if confirmation!='CANCEL '+identifier:raise PermissionError('Canceling requires the exact confirmation phrase')
        self._request('DELETE','calendars/primary/events/'+quote(identifier,safe=''))
        return {'confirmed':True,'id':identifier,'status':'cancelled'}

    @staticmethod
    def _text(value,label,limit):
        if not isinstance(value,str) or not value.strip() or len(value)>limit or '\r' in value or '\n' in value:
            raise ValueError(f'{label} must be 1–{limit} characters')
        return value.strip()

    @classmethod
    def _id(cls,value):return cls._text(value,'Event ID',200)
