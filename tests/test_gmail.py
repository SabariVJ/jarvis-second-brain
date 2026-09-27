import base64
import unittest
from unittest.mock import Mock

from jarvis.integrations.gmail import GmailAdapter
from jarvis.integrations.google_oauth import GoogleOAuth, TOKEN_URL


class Auth:
    configured=True
    def access_token(self):return 'mock-access-token'


def header(name,value):return {'name':name,'value':value}


class GmailTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        text=base64.urlsafe_b64encode(b'The release deadline is Friday. Please confirm the schedule.').decode().rstrip('=')
        self.thread_message={'id':'m1','threadId':'t1','snippet':'Release deadline Friday.', 'labelIds':['INBOX','UNREAD'],
            'payload':{'mimeType':'text/plain','body':{'data':text},'headers':[
                header('From','A Person <person@example.com>'),header('To','me@example.com'),
                header('Subject','Release plan'),header('Date','Mon, 01 Jan 2026 00:00:00 +0000')]}}
        def transport(method,url,token,payload=None):
            self.calls.append((method,url,token,payload))
            if method=='GET' and url.endswith('/messages?q=in%3Ainbox&maxResults=20'):
                return {'messages':[{'id':'m1'}],'resultSizeEstimate':1}
            if method=='GET' and '/messages/m1?' in url:return self.thread_message
            if method=='GET' and '/threads/t1?' in url:return {'id':'t1','messages':[self.thread_message]}
            if method=='POST' and url.endswith('/drafts'):return {'id':'d1','message':{'threadId':payload['message'].get('threadId')}}
            if method=='POST' and url.endswith('/drafts/send'):return {'id':'sent1','threadId':'t1'}
            return {}
        self.transport=transport;self.gmail=GmailAdapter(oauth=Auth(),transport=transport)

    def test_inbox_unread_search_thread_summary_and_provenance(self):
        inbox=self.gmail.list_messages('inbox')
        self.assertEqual(inbox['messages'][0]['subject'],'Release plan');self.assertTrue(inbox['messages'][0]['unread'])
        self.gmail.list_messages('unread');self.gmail.list_messages('search','from:person@example.com')
        self.assertIn('is%3Aunread',self.calls[2][1]);self.assertIn('from%3Aperson',self.calls[3][1])
        thread=self.gmail.thread('t1');self.assertIn('deadline is Friday',thread['messages'][0]['body'])
        summary=self.gmail.summarize('t1');self.assertEqual(summary['mode'],'local extract')
        self.assertIn('untrusted',summary['warning'])

    def test_new_and_reply_drafts_are_saved_without_sending(self):
        created=self.gmail.create_draft('person@example.com','A plan','I will follow up.')
        self.assertEqual(created['id'],'d1');self.assertTrue(self.calls[-1][3]['message']['raw'])
        reply=self.gmail.reply_draft('t1','Thank you.');payload=self.calls[-1][3]['message']
        self.assertEqual(reply['id'],'d1');self.assertEqual(payload['threadId'],'t1')
        self.assertEqual(self.calls[-1][0],'POST');self.assertTrue(self.calls[-1][1].endswith('/drafts'))

    def test_sending_requires_exact_confirmation_and_api_response(self):
        before=len(self.calls)
        with self.assertRaises(PermissionError):self.gmail.send_draft('d1','yes')
        self.assertEqual(len(self.calls),before)
        result=self.gmail.send_draft('d1','SEND d1');self.assertEqual(result['id'],'sent1')

    def test_not_connected_is_visible_and_never_calls_transport(self):
        transport=Mock();gmail=GmailAdapter(oauth=GoogleOAuth(env={}),transport=transport)
        self.assertEqual(gmail.status()['state'],'NOT CONNECTED')
        with self.assertRaisesRegex(ValueError,'not connected'):gmail.list_messages()
        transport.assert_not_called()

    def test_validation_blocks_header_injection_and_unbounded_queries(self):
        for args in [('\nBcc: x@example.com','subject','body'),('x@example.com','bad\nsubject','body'),
                     ('not-address','subject','body')]:
            with self.subTest(args=args),self.assertRaises(ValueError):self.gmail.create_draft(*args)
        with self.assertRaises(ValueError):self.gmail.list_messages('search','q'*301)

    def test_google_oauth_refreshes_and_caches_without_logging_secrets(self):
        env={'JARVIS_GOOGLE_CLIENT_ID':'id','JARVIS_GOOGLE_CLIENT_SECRET':'secret','JARVIS_GOOGLE_REFRESH_TOKEN':'refresh'}
        clock=Mock(return_value=1000);requester=Mock(return_value={'access_token':'short-lived','expires_in':3600})
        oauth=GoogleOAuth(env=env,requester=requester,clock=clock)
        self.assertEqual(oauth.access_token(),'short-lived');self.assertEqual(oauth.access_token(),'short-lived')
        requester.assert_called_once_with(TOKEN_URL,{'client_id':'id','client_secret':'secret','refresh_token':'refresh','grant_type':'refresh_token'})
        clock.return_value=4600;self.assertEqual(oauth.access_token(),'short-lived');self.assertEqual(requester.call_count,2)


if __name__=='__main__':unittest.main()
