"""On-demand, local morning briefing assembled from existing Jarvis systems."""
from datetime import datetime, timezone


class MorningBriefing:
    def __init__(self,database,gmail,calendar,focus,clock=None):
        self.database=database;self.gmail=gmail;self.calendar=calendar;self.focus=focus
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def _brain(self):
        with self.database.connect() as db:
            priorities=[dict(r) for r in db.execute('''SELECT m.category,m.content,s.relative_path AS source
                FROM memories m JOIN sources s ON s.id=m.source_id WHERE s.status='active'
                AND (lower(m.category) LIKE '%priorit%' OR lower(m.category) LIKE '%important%'
                  OR lower(m.content) LIKE '%priority%') ORDER BY m.created DESC LIMIT 8''')]
            deadlines=[dict(r) for r in db.execute('''SELECT m.category,m.content,s.relative_path AS source
                FROM memories m JOIN sources s ON s.id=m.source_id WHERE s.status='active'
                AND (lower(m.category) LIKE '%deadline%' OR lower(m.category) LIKE '%reminder%'
                  OR lower(m.content) LIKE '%deadline%') ORDER BY m.created DESC LIMIT 8''')]
            tasks=[dict(r) for r in db.execute('''SELECT t.title,t.status,s.relative_path AS source
                FROM tasks t JOIN sources s ON s.id=t.source_id WHERE s.status='active'
                AND lower(t.status) NOT IN ('done','completed','cancelled','canceled') ORDER BY t.title LIMIT 12''')]
            projects=[dict(r) for r in db.execute('''SELECT p.name,s.relative_path AS source,s.modified
                FROM projects p JOIN sources s ON s.id=p.source_id WHERE s.status='active'
                ORDER BY s.modified DESC,p.name LIMIT 6''')]
        clip=lambda item,fields,limit:{**item,**{key:str(item.get(key,'') or '')[:limit] for key in fields}}
        priorities=[clip(item,('category','content','source'),1000) for item in priorities]
        deadlines=[clip(item,('category','content','source'),1000) for item in deadlines]
        tasks=[clip(item,('title','status','source'),300) for item in tasks]
        projects=[clip(item,('name','source'),300) for item in projects]
        return {'priorities':priorities,'deadlines':deadlines,'reminders':deadlines,
            'active_tasks':tasks,'recent_projects':projects}

    def run(self):
        now=self.clock().astimezone()
        data={'generated_at':now.isoformat(),'calendar':{'status':'UNAVAILABLE','items':[]},
            'email':{'status':'UNAVAILABLE','items':[]},'brain':{},'focus':{'state':'IDLE'},
            'scheduling':{'supported':False,'auto_at_startup':False}}
        try:
            result=self.calendar.today();data['calendar']={'status':'READY','items':result.get('items',[])[:20]}
        except Exception:
            data['calendar']={'status':'NOT CONNECTED' if not self.calendar.connected else 'UNAVAILABLE','items':[]}
        try:
            result=self.gmail.list_messages('search','{is:important is:starred} newer_than:14d',10)
            data['email']={'status':'READY','items':result.get('messages',[])[:10]}
        except Exception:
            data['email']={'status':'NOT CONNECTED' if not self.gmail.connected else 'UNAVAILABLE','items':[]}
        try:data['brain']=self._brain()
        except Exception:data['brain']={'priorities':[],'deadlines':[],'reminders':[],'active_tasks':[],'recent_projects':[]}
        try:
            focus=self.focus.status();data['focus']={k:focus.get(k) for k in ('state','goal','remaining_seconds','result') if k in focus}
        except Exception:data['focus']={'state':'UNAVAILABLE'}
        brain=data['brain'];parts=['Good morning.']
        if data['calendar']['status']=='READY':parts.append(f"You have {len(data['calendar']['items'])} calendar item(s) today.")
        else:parts.append('Calendar is not connected.')
        if data['email']['status']=='READY':parts.append(f"There are {len(data['email']['items'])} important or starred email(s) from the last two weeks.")
        else:parts.append('Gmail is not connected.')
        if brain['active_tasks']:parts.append(f"You have {len(brain['active_tasks'])} active task(s).")
        if brain['deadlines']:parts.append(f"There are {len(brain['deadlines'])} saved deadline or reminder note(s).")
        if brain['priorities']:parts.append('Your top saved priority is '+brain['priorities'][0]['content'][:180].strip()+'.')
        focus=data['focus']
        if focus.get('state') in ('ACTIVE','PAUSED'):parts.append(f"Your focus target is {focus.get('goal','your current goal')}.")
        data['spoken']=' '.join(parts)
        return data
