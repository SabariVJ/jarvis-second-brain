"""Opt-in Telegram long polling with strict sender and artifact boundaries."""
from datetime import datetime, timezone
from io import BytesIO
import json
import os
import re
from threading import Event, Lock, Thread
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, quote
from urllib.request import Request, urlopen

API_ROOT='https://api.telegram.org/bot'
FILE_ROOT='https://api.telegram.org/file/bot'
MAX_VOICE_BYTES=10_000_000
_SHARE=re.compile(r'^share\s+(doc_[a-f0-9]{16,40})$',re.I)


def _http_json(method,url,payload=None,timeout=35):
    body=(payload if isinstance(payload,bytes) else json.dumps(payload).encode('utf-8')) if payload is not None else None
    headers={'Accept':'application/json'}
    if body is not None:headers['Content-Type']='multipart/form-data; boundary=----JarvisTelegramUpload' if isinstance(payload,bytes) else 'application/json'
    req=Request(url,data=body,headers=headers,method=method)
    try:
        with urlopen(req,timeout=timeout) as response:
            raw=response.read(1_000_000)
            result=json.loads(raw) if raw else {}
            if not result.get('ok'):raise ValueError('Telegram request was rejected')
            return result.get('result')
    except HTTPError as error:
        raise ValueError('Telegram request failed; check local bot configuration and network access') from None
    except (URLError,TimeoutError,OSError,json.JSONDecodeError):
        raise ValueError('Telegram is unavailable; check local bot configuration and network access') from None


class TelegramAdapter:
    def __init__(self, token=None, allowed_user_ids=None, enabled=None, transport=_http_json,
                 file_transport=None, on_text=None, transcriber=None, artifact_provider=None):
        self.token=token if token is not None else os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
        raw=allowed_user_ids if allowed_user_ids is not None else os.environ.get('TELEGRAM_ALLOWED_USER_IDS','')
        self.allowed_user_ids={str(item).strip() for item in (raw.split(',') if isinstance(raw,str) else raw) if str(item).strip().isdigit()}
        self.enabled=(os.environ.get('JARVIS_TELEGRAM_ENABLED','')=='1') if enabled is None else bool(enabled)
        self.transport=transport
        self.file_transport=file_transport or self._download_file
        self.on_text=on_text
        self.transcriber=transcriber
        self.artifact_provider=artifact_provider
        self._offset=None;self._thread=None;self._stop=Event();self._lock=Lock();self._pending_shares={}
        self.last_error=None;self.last_poll_at=None

    @property
    def configured(self):return bool(self.token and self.allowed_user_ids)

    def status(self):
        running=bool(self._thread and self._thread.is_alive())
        if not self.enabled:state='DISABLED'
        elif not self.configured:state='NOT CONNECTED'
        elif self._stop.is_set() and running:state='STOPPING'
        elif self.last_error:state='ERROR'
        else:state='CONNECTED' if running else 'READY'
        return {'state':state,'enabled':self.enabled,'configured':self.configured,'running':running,
            'allowed_user_count':len(self.allowed_user_ids),'voice_notes':'READY' if self.transcriber else 'NOT CONNECTED',
            'last_error':self.last_error,'sharing':'LOCAL APPROVAL REQUIRED'}

    def _url(self,method):return API_ROOT+self.token+'/'+method

    def _call(self,method,payload=None,timeout=35):
        if not self.configured:raise ValueError('Telegram is not connected. Configure the bot token and allowed user IDs locally.')
        url=self._url(method)
        if payload is not None and method in ('getUpdates','getFile'):url+='?'+urlencode(payload)
        return self.transport('POST' if payload is not None and method not in ('getUpdates','getFile') else 'GET',url,
            None if method in ('getUpdates','getFile') else payload,timeout)

    def start(self):
        if not self.enabled:raise ValueError('Telegram is disabled. Enable it locally before starting remote access.')
        if not self.configured:raise ValueError('Telegram is not connected. Configure the bot token and allowed user IDs locally.')
        with self._lock:
            if self._thread and self._thread.is_alive():return self.status()
            self._stop.clear();self.last_error=None
            self._thread=Thread(target=self._poll_loop,name='jarvis-telegram-poll',daemon=True);self._thread.start()
        return self.status()

    def stop(self):
        self._stop.set()
        return self.status()

    def poll_once(self):
        updates=self._call('getUpdates',{'timeout':20,'allowed_updates':json.dumps(['message'])},timeout=25) or []
        processed=0
        for update in updates:
            if not isinstance(update,dict):continue
            try:self._offset=max(self._offset or 0,int(update.get('update_id',0))+1)
            except (TypeError,ValueError):continue
            if self.process_update(update):processed+=1
        self.last_poll_at=datetime.now(timezone.utc).isoformat()
        return {'processed':processed,'offset':self._offset}

    def _poll_loop(self):
        while not self._stop.is_set():
            try:self.poll_once();self.last_error=None
            except ValueError as error:
                self.last_error=str(error)
                self._stop.wait(3)
            except Exception:
                self.last_error='Telegram polling failed; no message was delivered.'
                self._stop.wait(3)

    def process_update(self,update):
        """Authorize by private-chat sender before reading message text, files, or commands."""
        message=update.get('message') if isinstance(update,dict) else None
        if not isinstance(message,dict):return False
        sender=message.get('from') or {};chat=message.get('chat') or {}
        sender_id=str(sender.get('id',''))
        if chat.get('type')!='private' or not sender_id.isdigit() or sender_id not in self.allowed_user_ids:return False
        chat_id=str(chat.get('id',''))
        if not chat_id.isdigit():return False
        text=message.get('text')
        if isinstance(text,str) and text.strip():self._handle_text(chat_id,sender_id,text.strip())
        elif isinstance(message.get('voice'),dict):self._handle_voice(chat_id,message['voice'],sender_id)
        return True

    def _send_text(self,chat_id,text):
        text=str(text or 'Jarvis could not produce a response.')[:4000]
        return self._call('sendMessage',{'chat_id':chat_id,'text':text})

    def _handle_text(self,chat_id,sender_id,text):
        match=_SHARE.fullmatch(text)
        if match:
            self._confirm_share(chat_id,match.group(1));return
        if re.fullmatch(r'/share(?:@\w+)?(?:\s+latest)?',text,re.I):
            self._request_share(chat_id);return
        if text.startswith('/') and text.casefold() not in ('/start','/help'):
            self._send_text(chat_id,'That command is not available.');return
        if text.casefold() in ('/start','/help'):
            self._send_text(chat_id,'Jarvis remote is active. Send a message, a voice note, or /share latest for a locally approved generated document.');return
        if self.on_text is None:self._send_text(chat_id,'Jarvis chat is not available in this session.');return
        try:
            response=self.on_text(sender_id,text)
            if isinstance(response,dict):response=response.get('answer','')
            self._send_text(chat_id,response)
        except Exception:self._send_text(chat_id,'Jarvis could not complete that request. Local data was preserved.')

    def _handle_voice(self,chat_id,voice,sender_id):
        if self.transcriber is None:
            self._send_text(chat_id,'Voice-note transcription is not connected. Configure the local transcription provider first.');return
        try:
            size=int(voice.get('file_size',0))
            if size<1 or size>MAX_VOICE_BYTES:raise ValueError
            info=self._call('getFile',{'file_id':str(voice.get('file_id',''))})
            remote_path=info.get('file_path') if isinstance(info,dict) else None
            if not isinstance(remote_path,str) or not remote_path or '..' in remote_path.split('/') or remote_path.startswith('/'):
                raise ValueError
            audio=self.file_transport(remote_path,MAX_VOICE_BYTES)
            if not isinstance(audio,bytes) or not audio or len(audio)>MAX_VOICE_BYTES:raise ValueError
            transcript=self.transcriber(audio,remote_path.rsplit('/',1)[-1])
            if not isinstance(transcript,str) or not transcript.strip():raise ValueError
            # The sender was already allowlisted in process_update; memory capture remains
            # disabled for transcribed audio unless the transcript is an explicit command.
            if self.on_text is None:raise ValueError
            response=self.on_text(sender_id,transcript.strip())
            self._send_text(chat_id,response.get('answer','') if isinstance(response,dict) else response)
        except Exception:self._send_text(chat_id,'I could not transcribe that voice note. The audio was discarded.')

    def _download_file(self,remote_path,max_bytes):
        url=FILE_ROOT+self.token+'/'+quote(remote_path,safe='/')
        try:
            with urlopen(Request(url,headers={'Accept':'application/octet-stream'}),timeout=25) as response:
                raw=response.read(max_bytes+1)
                if len(raw)>max_bytes:raise ValueError('Voice note exceeds the local size limit')
                return raw
        except (HTTPError,URLError,TimeoutError,OSError):raise ValueError('Telegram voice file was unavailable') from None

    def _request_share(self,chat_id):
        if self.artifact_provider is None:
            self._send_text(chat_id,'No generated document sharing is configured.');return
        artifact=self.artifact_provider('latest',False)
        if not artifact:
            self._send_text(chat_id,'No locally approved generated documents are available to share.');return
        if not artifact.get('share_approved'):
            self._send_text(chat_id,'Sharing is off for that document. Approve sharing on its local Jarvis card first.');return
        self._pending_shares[chat_id]=(artifact['id'],datetime.now(timezone.utc).timestamp()+300)
        self._send_text(chat_id,f"To send {artifact['filename']} to this Telegram chat, reply SHARE {artifact['id']} within five minutes.")

    def _confirm_share(self,chat_id,artifact_id):
        pending=self._pending_shares.get(chat_id)
        if not pending or pending[0]!=artifact_id or pending[1]<datetime.now(timezone.utc).timestamp():
            self._pending_shares.pop(chat_id,None);self._send_text(chat_id,'No current sharing confirmation matches that document.');return
        if self.artifact_provider is None:
            self._send_text(chat_id,'Document sharing is unavailable.');return
        artifact=self.artifact_provider(artifact_id,True)
        if not artifact or not artifact.get('share_approved'):
            self._send_text(chat_id,'That document is no longer approved for sharing.');return
        self._send_document(chat_id,artifact['filename'],artifact['content'])
        self._pending_shares.pop(chat_id,None)
        self._send_text(chat_id,'Telegram confirmed the document was sent.')

    def _send_document(self,chat_id,filename,content):
        if not isinstance(content,bytes) or len(content)>10_000_000:raise ValueError('Generated document is outside the sharing size limit')
        boundary='----JarvisTelegramUpload'
        safe_name=re.sub(r'[^A-Za-z0-9._ -]','_',str(filename))[:120] or 'document.pdf'
        parts=[f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="document"; filename="{safe_name}"\r\nContent-Type: application/pdf\r\n\r\n'.encode(),content,
            f'\r\n--{boundary}--\r\n'.encode()]
        self.transport('POST',self._url('sendDocument'),b''.join(parts),timeout=35)
