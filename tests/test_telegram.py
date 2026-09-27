import unittest
from jarvis.integrations.telegram import TelegramAdapter, MAX_VOICE_BYTES


def update(user_id=17,text='hello',chat_type='private',voice=None):
    message={'from':{'id':user_id},'chat':{'id':user_id,'type':chat_type}}
    if voice is not None:message['voice']=voice
    else:message['text']=text
    return {'update_id':3,'message':message}


class TelegramTests(unittest.TestCase):
    def test_disabled_or_missing_configuration_is_explicit_and_token_is_not_exposed(self):
        bot=TelegramAdapter(token='secret-token',allowed_user_ids=['17'],enabled=False)
        self.assertEqual(bot.status()['state'],'DISABLED')
        self.assertNotIn('secret-token',str(bot.status()))
        with self.assertRaisesRegex(ValueError,'disabled'):bot.start()
        missing=TelegramAdapter(token='',allowed_user_ids=[],enabled=True)
        self.assertEqual(missing.status()['state'],'NOT CONNECTED')
        with self.assertRaisesRegex(ValueError,'not connected'):missing.start()

    def test_only_allowlisted_private_senders_are_processed(self):
        calls=[];sent=[]
        bot=TelegramAdapter('test',['17'],True,on_text=lambda uid,text:calls.append((uid,text)) or {'answer':'Got it'},
            transport=lambda method,url,payload=None,timeout=35: sent.append(payload) or {'message_id':1})
        self.assertFalse(bot.process_update(update(18,'secret from outsider')))
        self.assertFalse(bot.process_update(update(17,'group message','group')))
        self.assertEqual(calls,[]);self.assertEqual(sent,[])
        self.assertTrue(bot.process_update(update(17,'hello Jarvis')))
        self.assertEqual(calls,[('17','hello Jarvis')]);self.assertEqual(sent[0]['text'],'Got it')

    def test_poll_advances_offset_even_when_messages_are_unauthorized(self):
        received=[]
        def transport(method,url,payload=None,timeout=35):
            received.append((method,url));return [update(99,'no')]
        bot=TelegramAdapter('test',['17'],True,transport=transport)
        self.assertEqual(bot.poll_once(),{'processed':0,'offset':4})
        self.assertNotIn('offset=',received[0][1])

    def test_voice_note_is_bounded_transient_and_reuses_authorized_chat(self):
        calls=[];transcribed=[]
        def transport(method,url,payload=None,timeout=35):
            calls.append((method,url,payload))
            if 'getFile' in url:return {'file_path':'voice/file_1.oga'}
            return {'message_id':1}
        bot=TelegramAdapter('test',['17'],True,transport=transport,
            file_transport=lambda path,limit:b'ephemeral audio',
            transcriber=lambda audio,name:transcribed.append((audio,name)) or 'Jarvis, remember that I prefer short reports.',
            on_text=lambda uid,text:{'answer':'Saved from explicit request'})
        self.assertTrue(bot.process_update(update(17,voice={'file_id':'f1','file_size':12})))
        self.assertEqual(transcribed,[ (b'ephemeral audio','file_1.oga') ])
        self.assertEqual(calls[-1][2]['text'],'Saved from explicit request')
        bot.process_update(update(17,voice={'file_id':'f2','file_size':MAX_VOICE_BYTES+1}))
        self.assertEqual(len(transcribed),1)

    def test_voice_file_path_is_validated_before_download(self):
        downloaded=[]
        bot=TelegramAdapter('test',['17'],True,transport=lambda method,url,payload=None,timeout=35:{'file_path':'../secrets'},
            file_transport=lambda path,limit:downloaded.append(path),transcriber=lambda *_:'x',on_text=lambda *_:'x')
        bot.process_update(update(17,voice={'file_id':'f','file_size':10}))
        self.assertEqual(downloaded,[])

    def test_sharing_requires_local_approval_then_exact_in_chat_confirmation(self):
        calls=[];sent=[];artifact={'id':'doc_0123456789abcdef','filename':'invoice_1.pdf','content':b'%PDF-test','share_approved':True}
        def transport(method,url,payload=None,timeout=35):calls.append((method,url,payload));return {'message_id':1}
        bot=TelegramAdapter('test',['17'],True,transport=transport,artifact_provider=lambda ref,include:artifact if ref in ('latest',artifact['id']) else None)
        bot.process_update(update(17,'/share latest'))
        self.assertIn('SHARE '+artifact['id'],calls[-1][2]['text'])
        bot.process_update(update(17,'share doc_fedcba9876543210'))
        self.assertNotIn('sendDocument',calls[-1][1])
        bot.process_update(update(17,'/share latest'))
        bot.process_update(update(17,'SHARE '+artifact['id']))
        upload=next(call for call in calls if 'sendDocument' in call[1])
        self.assertIn(b'invoice_1.pdf',upload[2]);self.assertIn(b'%PDF-test',upload[2])
        self.assertNotIn(b'..',upload[2])

    def test_document_sharing_never_resolves_unapproved_artifact(self):
        calls=[];payloads=[]
        bot=TelegramAdapter('test',['17'],True,transport=lambda method,url,payload=None,timeout=35:(calls.append(url),payloads.append(payload)) or {'message_id':1},
            artifact_provider=lambda *_:{'id':'doc_0123456789abcdef','filename':'private.pdf','content':b'x','share_approved':False})
        bot.process_update(update(17,'/share latest'))
        self.assertFalse(any('sendDocument' in url for url in calls))
        self.assertIn('Sharing is off',payloads[0]['text'])


if __name__=='__main__':unittest.main()
