"""Opt-in Windows foreground-app focus timer; raw window titles are never stored."""
import ctypes
import json
import os
from pathlib import Path
import threading
import time
import uuid

DEFAULT_ALLOWED = ['code.exe', 'devenv.exe', 'pycharm64.exe', 'idea64.exe', 'notepad++.exe']
DEFAULT_DISTRACTIONS = ['instagram', 'tiktok', 'facebook', 'youtube', 'reddit', 'twitter.com']


def active_windows_window():
    """Return just the foreground process and title. Never captures keys or pixels."""
    if os.name != 'nt':
        return None
    try:
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        user32.GetForegroundWindow.restype=wintypes.HWND
        user32.GetWindowTextLengthW.argtypes=[wintypes.HWND];user32.GetWindowTextLengthW.restype=ctypes.c_int
        user32.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int];user32.GetWindowTextW.restype=ctypes.c_int
        user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
        user32.GetWindowThreadProcessId.restype=wintypes.DWORD
        kernel32.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel32.OpenProcess.restype=wintypes.HANDLE
        kernel32.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
        kernel32.QueryFullProcessImageNameW.restype=wintypes.BOOL
        kernel32.CloseHandle.argtypes=[wintypes.HANDLE];kernel32.CloseHandle.restype=wintypes.BOOL
        hwnd = user32.GetForegroundWindow()
        if not hwnd: return None
        length = user32.GetWindowTextLengthW(hwnd)
        title_buffer = ctypes.create_unicode_buffer(min(max(length + 1, 2), 1024))
        user32.GetWindowTextW(hwnd, title_buffer, len(title_buffer))
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        handle = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle: return {'process':'', 'title':title_buffer.value[:240]}
        try:
            image_buffer=ctypes.create_unicode_buffer(1024);size=ctypes.c_ulong(len(image_buffer))
            if not kernel32.QueryFullProcessImageNameW(handle,0,image_buffer,ctypes.byref(size)):
                return {'process':'', 'title':title_buffer.value[:240]}
            return {'process':Path(image_buffer.value).name.casefold(), 'title':title_buffer.value[:240]}
        finally: kernel32.CloseHandle(handle)
    except Exception:
        return None


class FocusLock:
    def __init__(self, path, sampler=None, clock=time.time, worker=True, interval=5):
        self.path=Path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        self.sampler=sampler or active_windows_window;self.clock=clock;self.worker=worker;self.interval=interval
        self.lock=threading.RLock();self.stop_event=threading.Event();self.thread=None
        self.last_bucket=None;self.last_alert=0;self.alerts=[]
        self.session,self.history=self._load()
        if self.worker and self.session and self.session['state']=='ACTIVE':self._start_worker()

    def _load(self):
        try:
            value=json.loads(self.path.read_text(encoding='utf-8'))
            if isinstance(value,dict) and 'session' in value:
                session=value.get('session');history=value.get('history',[])
                return (session if isinstance(session,dict) and session.get('state') in ('ACTIVE','PAUSED','COMPLETED','STOPPED') else None,
                    history[-100:] if isinstance(history,list) else [])
            if isinstance(value,dict) and value.get('state') in ('ACTIVE','PAUSED','COMPLETED','STOPPED'):
                return value,[]
        except (OSError,ValueError,TypeError): pass
        return None,[]

    def _save(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps({'session':self.session,'history':self.history[-100:]},ensure_ascii=False),encoding='utf-8')
        os.replace(tmp,self.path)

    def _archive(self):
        if not self.session or self.session.get('_archived'):return
        self.history.append({k:self.session.get(k) for k in ('id','goal','started_at','ended_at','duration_seconds',
            'focused_seconds','distraction_count','pause_count','result')})
        self.history=self.history[-100:];self.session['_archived']=True

    def _start_worker(self):
        self.stop_event=threading.Event();self.thread=threading.Thread(target=self._run,daemon=True,name='jarvis-focus-sampler');self.thread.start()

    @staticmethod
    def _rules(values, default):
        if values is None: values=default
        if not isinstance(values,list) or len(values)>30: raise ValueError('Focus rules must be lists of up to 30 names')
        cleaned=[]
        for value in values:
            if not isinstance(value,str) or not value.strip() or len(value)>64: raise ValueError('Each focus rule must be 1–64 characters')
            item=value.strip().casefold()
            if item not in cleaned:cleaned.append(item)
        return cleaned

    def start(self, minutes=90, goal='Focus session', allowed_apps=None, distractions=None):
        try: minutes=int(minutes)
        except (ValueError,TypeError): raise ValueError('Focus duration must be 1–480 minutes') from None
        if not 1<=minutes<=480: raise ValueError('Focus duration must be 1–480 minutes')
        if not isinstance(goal,str) or not goal.strip() or len(goal)>120: raise ValueError('Focus goal must be 1–120 characters')
        allowed=self._rules(allowed_apps,DEFAULT_ALLOWED);distracting=self._rules(distractions,DEFAULT_DISTRACTIONS)
        now=self.clock()
        with self.lock:
            if self.session and self.session['state'] in ('ACTIVE','PAUSED'):
                raise ValueError('Stop or pause the current focus session before starting another')
            self.stop_event.set()
            self.session={'id':uuid.uuid4().hex,'state':'ACTIVE','started_at':now,'duration_seconds':minutes*60,
                'goal':goal.strip(),'allowed_apps':allowed,'distractions':distracting,'pause_count':0,
                'distraction_count':0,'focused_seconds':0,'paused_seconds':0,'ended_at':None,'result':None,
                '_paused_at':None,'_distraction_seconds':0,'_archived':False}
            self.last_bucket=None;self.last_alert=0;self.alerts=[];self._save()
            if self.worker:self._start_worker()
            return self.status()

    def _run(self):
        while not self.stop_event.wait(self.interval):
            try:self.sample_once()
            except Exception:pass

    def _elapsed(self, now):
        s=self.session
        paused=s.get('_paused_at')
        end=paused if s['state']=='PAUSED' and paused else now
        return max(0,min(s['duration_seconds'],end-s['started_at']-s.get('paused_seconds',0)))

    def _finish_if_due(self, now):
        if self.session and self.session['state']=='ACTIVE' and self._elapsed(now)>=self.session['duration_seconds']:
            self.session['state']='COMPLETED';self.session['ended_at']=now;self.session['result']='completed'
            self.session['focused_seconds']=self.session['duration_seconds']-self.session.get('_distraction_seconds',0)
            self._archive();self.stop_event.set();self._save()

    def sample_once(self):
        with self.lock:
            now=self.clock();self._finish_if_due(now)
            if not self.session or self.session['state']!='ACTIVE':return self._status(False)
            try:window=self.sampler()
            except Exception:window=None
            if not isinstance(window,dict):return self._status(False)
            process=str(window.get('process',''))[:100].casefold();title=str(window.get('title',''))[:240].casefold()
            haystack=process+' '+title
            rule=next((x for x in self.session['distractions'] if x in haystack),None)
            bucket='distracting' if rule else ('allowed' if any(x in haystack for x in self.session['allowed_apps']) else 'neutral')
            if bucket=='distracting':
                if self.last_bucket!='distracting' or now-self.last_alert>=120:
                    self.session['distraction_count']+=1;self.last_alert=now
                    remaining=max(0,round((self.session['duration_seconds']-self._elapsed(now))/60))
                    label=(rule.capitalize() if rule else 'This app')
                    self.alerts.append(f'{label} can wait. You have {remaining} minutes left.')
                self.session['_distraction_seconds']+=min(self.interval,30)
            self.last_bucket=bucket
            self.session['focused_seconds']=max(0,int(self._elapsed(now)-self.session.get('_distraction_seconds',0)))
            self._finish_if_due(now);self._save();return self._status(False)

    def pause(self):
        with self.lock:
            if not self.session or self.session['state']!='ACTIVE':raise ValueError('No active focus session to pause')
            now=self.clock();self.session['focused_seconds']=max(0,int(self._elapsed(now)-self.session.get('_distraction_seconds',0)))
            self.session['state']='PAUSED';self.session['_paused_at']=now;self.session['pause_count']+=1
            self._save();return self.status()

    def resume(self):
        with self.lock:
            if not self.session or self.session['state']!='PAUSED':raise ValueError('No paused focus session to resume')
            now=self.clock();self.session['paused_seconds']+=max(0,now-self.session['_paused_at']);self.session['_paused_at']=None
            self.session['state']='ACTIVE';self.last_bucket=None;self._save();return self.status()

    def stop(self):
        with self.lock:
            if not self.session or self.session['state'] not in ('ACTIVE','PAUSED'):raise ValueError('No running focus session to stop')
            now=self.clock();self.session['focused_seconds']=max(0,int(self._elapsed(now)-self.session.get('_distraction_seconds',0)))
            self.session['state']='STOPPED';self.session['ended_at']=now
            self.session['result']='completed' if self._elapsed(now)>=self.session['duration_seconds'] else 'stopped'
            self._archive();self.stop_event.set();self._save();return self.status()

    def status(self):
        return self._status(True)

    def _status(self, pop_alert):
        with self.lock:
            now=self.clock()
            if self.session:self._finish_if_due(now)
            supported=os.name=='nt' or self.sampler is not active_windows_window
            if not self.session:
                result={'state':'IDLE','monitor_supported':supported,'warning':None}
            else:
                elapsed=self._elapsed(now)
                result={'state':self.session['state'],'session_id':self.session['id'],'goal':self.session['goal'],
                    'duration_seconds':self.session['duration_seconds'],'remaining_seconds':max(0,int(self.session['duration_seconds']-elapsed)),
                    'focused_seconds':self.session.get('focused_seconds',0),'distraction_count':self.session['distraction_count'],
                    'pause_count':self.session['pause_count'],'result':self.session['result'],'monitor_supported':supported,
                    'allowed_apps':self.session['allowed_apps'],'distractions':self.session['distractions'],
                    'started_at':self.session['started_at'],'ended_at':self.session['ended_at'],'recent_sessions':self.history[-10:],
                    'warning':self.alerts.pop(0) if pop_alert and self.alerts else None}
            return result
