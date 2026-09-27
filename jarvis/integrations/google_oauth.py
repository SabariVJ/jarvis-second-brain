"""Minimal Google refresh-token client. Credentials are read from the process environment."""
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TOKEN_URL='https://oauth2.googleapis.com/token'


def _post_token(url, form):
    request=Request(url,data=urlencode(form).encode(),headers={'Content-Type':'application/x-www-form-urlencoded'},method='POST')
    try:
        with urlopen(request,timeout=20) as response:return json.loads(response.read(65536))
    except (HTTPError,URLError,TimeoutError,OSError,ValueError):
        raise ValueError('Google authorization failed. Check local OAuth setup and consent.') from None


class GoogleOAuth:
    def __init__(self, env=os.environ, requester=_post_token, clock=time.time):
        self.env=env;self.requester=requester;self.clock=clock;self.lock=threading.Lock()
        self._token=None;self._expires=0

    @property
    def configured(self):
        return all(self.env.get(k) for k in ('JARVIS_GOOGLE_CLIENT_ID','JARVIS_GOOGLE_CLIENT_SECRET','JARVIS_GOOGLE_REFRESH_TOKEN'))

    def access_token(self):
        if not self.configured:raise ValueError('Google integration is not connected')
        with self.lock:
            if self._token and self.clock()<self._expires-30:return self._token
            form={'client_id':self.env['JARVIS_GOOGLE_CLIENT_ID'],'client_secret':self.env['JARVIS_GOOGLE_CLIENT_SECRET'],
                'refresh_token':self.env['JARVIS_GOOGLE_REFRESH_TOKEN'],'grant_type':'refresh_token'}
            result=self.requester(TOKEN_URL,form)
            token=result.get('access_token') if isinstance(result,dict) else None
            if not isinstance(token,str) or not token:raise ValueError('Google authorization returned no access token')
            self._token=token;self._expires=self.clock()+max(60,int(result.get('expires_in',3600)))
            return self._token
