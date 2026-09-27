"""Narrow Windows helpers. No shell, key input or screenshot persistence."""
import os
from pathlib import Path
import platform
import subprocess
from urllib.parse import urlsplit
import webbrowser


class WindowsTools:
    APP_ALIASES={
        'vscode':'code','vs code':'code','visual studio code':'code','code':'code',
        'notepad':'notepad','text editor':'notepad','file explorer':'explorer','explorer':'explorer',
        'edge':'edge','microsoft edge':'edge','chrome':'chrome','google chrome':'chrome',
    }

    def __init__(self,allowed_roots=(),*,platform_name=None,applications=None,start_file=None,
                 start_process=None,active_window_provider=None,url_opener=None,volume_setter=None):
        self.platform_name=platform_name or platform.system();self.allowed_roots=[Path(p).resolve() for p in allowed_roots]
        self.applications=applications or self._discover_applications();self.start_file=start_file
        self.start_process=start_process or subprocess.Popen;self.active_window_provider=active_window_provider;self.url_opener=url_opener or webbrowser.open
        self.volume_setter=volume_setter

    @staticmethod
    def _discover_applications():
        windir=Path(os.environ.get('WINDIR',r'C:\Windows'))
        local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData'/'Local')))
        candidates={
            'notepad':[windir/'System32'/'notepad.exe'],
            'explorer':[windir/'explorer.exe'],
            'edge':[Path(os.environ.get('PROGRAMFILES(X86)',r'C:\Program Files (x86)'))/'Microsoft'/'Edge'/'Application'/'msedge.exe',
                    Path(os.environ.get('PROGRAMFILES',r'C:\Program Files'))/'Microsoft'/'Edge'/'Application'/'msedge.exe'],
            'chrome':[Path(os.environ.get('PROGRAMFILES',r'C:\Program Files'))/'Google'/'Chrome'/'Application'/'chrome.exe',
                      local/'Google'/'Chrome'/'Application'/'chrome.exe'],
            'code':[local/'Programs'/'Microsoft VS Code'/'Code.exe'],
        }
        return {name:str(chosen) for name,paths in candidates.items()
            if (chosen:=next((p for p in paths if p.is_file()),None)) is not None}

    def _windows(self):
        if self.platform_name!='Windows':raise ValueError('Windows controls are unavailable on this platform')

    def open_application(self,application):
        self._windows()
        if not isinstance(application,str) or len(application)>120:raise ValueError('Application name is invalid')
        key=self.APP_ALIASES.get(application.strip().casefold())
        if not key:raise ValueError('Application is not in Jarvis’s safe application allowlist')
        executable=self.applications.get(key)
        if not executable or not Path(executable).is_file():raise ValueError('This allowlisted application is not installed')
        self.start_process([str(Path(executable).resolve())],shell=False,close_fds=True)
        return {'opened':True,'application':key}

    def validate_request(self,name,args):
        if name=='open_application':
            self._windows();application=args.get('application','')
            if not isinstance(application,str) or self.APP_ALIASES.get(application.strip().casefold()) not in self.applications:
                raise ValueError('Application is not in Jarvis’s safe installed application allowlist')
        elif name=='open_file':self._path(args.get('path'),True)
        elif name=='open_folder':self._path(args.get('path'),False)
        elif name=='open_url':self._validate_url(args.get('url'))

    def _validate_url(self,url):
        self._windows()
        if not isinstance(url,str) or len(url)>2048:raise ValueError('URL is invalid')
        parsed=urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('Only public HTTP and HTTPS URLs without embedded credentials can be opened')
        host=parsed.hostname.casefold().rstrip('.')
        if host in ('localhost','localhost.localdomain') or host.endswith('.localhost') or host.endswith('.local'):
            raise ValueError('Local network URLs are not opened by this tool')
        return parsed

    def _path(self,value,must_be_file):
        if not isinstance(value,str) or not value or len(value)>1000:raise ValueError('Path is invalid')
        candidate=Path(value).expanduser().resolve(strict=True)
        if not any(candidate.is_relative_to(root) for root in self.allowed_roots):
            raise ValueError('Windows file access is restricted to indexed notes and generated documents')
        if must_be_file and not candidate.is_file():raise ValueError('File was not found')
        if not must_be_file and not candidate.is_dir():raise ValueError('Folder was not found')
        if must_be_file and candidate.suffix.casefold() in {'.exe','.com','.bat','.cmd','.ps1','.msi','.scr','.dll'}:
            raise ValueError('Executable and script files cannot be opened by this tool')
        return candidate

    def _start_file(self,path):
        self._windows()
        start=self.start_file or getattr(os,'startfile',None)
        if not start:raise ValueError('Windows file association support is unavailable')
        start(str(path))

    def open_file(self,path):
        candidate=self._path(path,True);self._start_file(candidate)
        return {'opened':True,'path':str(candidate)}

    def open_folder(self,path):
        candidate=self._path(path,False);self._start_file(candidate)
        return {'opened':True,'path':str(candidate)}

    def open_url(self,url):
        self._validate_url(url)
        opened=bool(self.url_opener(url,new=2,autoraise=True))
        if not opened:raise ValueError('The browser did not accept the URL')
        return {'opened':True,'url':url}

    def _foreground(self):
        if self.active_window_provider:return self.active_window_provider()
        self._windows()
        import ctypes
        user32=ctypes.windll.user32;hwnd=user32.GetForegroundWindow()
        if not hwnd:return {'application':'','title':''}
        length=user32.GetWindowTextLengthW(hwnd);buffer=ctypes.create_unicode_buffer(min(max(length+1,2),2049))
        user32.GetWindowTextW(hwnd,buffer,len(buffer));pid=ctypes.c_ulong();user32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        name=''
        kernel32=ctypes.windll.kernel32
        process=kernel32.OpenProcess(0x1000,False,pid.value)
        if process:
            try:
                capacity=ctypes.c_ulong(1024);path=ctypes.create_unicode_buffer(capacity.value)
                if kernel32.QueryFullProcessImageNameW(process,0,path,ctypes.byref(capacity)):name=Path(path.value).name
            finally:kernel32.CloseHandle(process)
        return {'application':name,'title':buffer.value[:200]}

    def get_active_application(self):return {'application':self._foreground().get('application','')}
    def get_active_window(self):return self._foreground()

    @staticmethod
    def get_system_info():
        return {'platform':platform.system(),'release':platform.release(),'python':platform.python_version()}

    def set_volume(self,percent):
        if not isinstance(percent,int) or isinstance(percent,bool) or not 0<=percent<=100:raise ValueError('Volume must be an integer from 0 to 100')
        if self.volume_setter:return self.volume_setter(percent)
        self._windows()
        import ctypes
        from ctypes import wintypes
        class GUID(ctypes.Structure):
            _fields_=[('Data1',wintypes.DWORD),('Data2',wintypes.WORD),('Data3',wintypes.WORD),('Data4',ctypes.c_ubyte*8)]
        def make_guid(value):
            a,b,c,d,e=value.split('-');tail=bytes.fromhex(d+e)
            return GUID(int(a,16),int(b,16),int(c,16),(ctypes.c_ubyte*8)(*tail))
        def call(pointer,index,result,args):
            table=ctypes.cast(pointer,ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
            return ctypes.WINFUNCTYPE(result,ctypes.c_void_p,*args)(table[index])
        ole=ctypes.windll.ole32
        ole.CoInitializeEx.argtypes=[ctypes.c_void_p,wintypes.DWORD];ole.CoInitializeEx.restype=wintypes.HRESULT
        init=ole.CoInitializeEx(None,0)
        if init<0 and init!=ctypes.c_long(0x80010106).value:raise OSError('Windows audio initialization failed')
        uninitialize=init>=0;enumerator=ctypes.c_void_p();device=ctypes.c_void_p();volume=ctypes.c_void_p()
        try:
            create=ole.CoCreateInstance;create.restype=wintypes.HRESULT
            create.argtypes=[ctypes.POINTER(GUID),ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(GUID),ctypes.POINTER(ctypes.c_void_p)]
            hr=create(ctypes.byref(make_guid('BCDE0395-E52F-467C-8E3D-C4579291692E')),None,23,
                ctypes.byref(make_guid('A95664D2-9614-4F35-A746-DE8DB63617E6')),ctypes.byref(enumerator))
            if hr<0:raise OSError('Windows audio device service is unavailable')
            hr=call(enumerator,4,wintypes.HRESULT,[wintypes.INT,wintypes.INT,ctypes.POINTER(ctypes.c_void_p)])(enumerator,0,1,ctypes.byref(device))
            if hr<0:raise OSError('Windows playback device is unavailable')
            hr=call(device,3,wintypes.HRESULT,[ctypes.POINTER(GUID),wintypes.DWORD,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)])(
                device,ctypes.byref(make_guid('5CDF2C82-841E-4546-9722-0CF74078229A')),23,None,ctypes.byref(volume))
            if hr<0:raise OSError('Windows master-volume control is unavailable')
            hr=call(volume,7,wintypes.HRESULT,[ctypes.c_float,ctypes.c_void_p])(volume,float(percent)/100.0,None)
            if hr<0:raise OSError('Windows did not confirm the volume change')
            return {'changed':True,'percent':percent}
        finally:
            for pointer in (volume,device,enumerator):
                if pointer.value:call(pointer,2,wintypes.ULONG,[])(pointer)
            if uninitialize:ole.CoUninitialize()

    @staticmethod
    def capture_screenshot():
        raise ValueError('Use Explain current screen once to choose a display. Captures are transient and are not saved.')
