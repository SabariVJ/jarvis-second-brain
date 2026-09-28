import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from jarvis.core.runtime import Runtime


class DegradedModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.notes=self.root/'notes';self.notes.mkdir()
        (self.notes/'svj.md').write_text('# SVJ\nThe SVJ rollout is scheduled for the July pilot.',encoding='utf-8')

    def test_no_credentials_or_network_keeps_local_brain_available(self):
        env=patch.dict(os.environ,{'JARVIS_DATA_DIR':str(self.root/'data'),'OPENAI_API_KEY':'',
            'JARVIS_EMBEDDINGS':'','GOOGLE_CLIENT_ID':'','GOOGLE_CLIENT_SECRET':'',
            'JARVIS_GOOGLE_CLIENT_ID':'','JARVIS_GOOGLE_CLIENT_SECRET':'','JARVIS_GOOGLE_REFRESH_TOKEN':'',
            'TELEGRAM_BOT_TOKEN':'','TELEGRAM_ALLOWED_USER_IDS':'','JARVIS_TELEGRAM_ENABLED':'0'})
        env.start();self.addCleanup(env.stop)
        with patch('socket.create_connection',side_effect=AssertionError('network access attempted')):
            runtime=Runtime(self.root,lambda:str(self.notes))
            self.assertFalse(runtime.brain.enabled);self.assertFalse(runtime.embeddings.enabled)
            self.assertFalse(runtime.research.enabled);self.assertFalse(runtime.vision.enabled)
            self.assertFalse(runtime.gmail.connected);self.assertFalse(runtime.calendar.connected)
            self.assertFalse(runtime.telegram.enabled);self.assertFalse(runtime.telegram.configured)
            runtime.gmail.transport=Mock(side_effect=AssertionError('Gmail transport attempted'))
            runtime.calendar.transport=Mock(side_effect=AssertionError('Calendar transport attempted'))
            runtime.provider_events.configure('GMAIL',True)
            runtime.provider_events.configure('CALENDAR',True)
            self.assertEqual(runtime.provider_events.run_due()['polled'],['CALENDAR','GMAIL'])
            self.assertEqual(runtime.provider_events.status()['GMAIL']['status'],'NOT CONNECTED')
            self.assertEqual(runtime.provider_events.status()['CALENDAR']['status'],'NOT CONNECTED')
            runtime.gmail.transport.assert_not_called();runtime.calendar.transport.assert_not_called()
            runtime.provider_events.configure('GMAIL',False)
            runtime.provider_events.configure('CALENDAR',False)
            session,context,state=runtime.sessions.get()
            answer=runtime.orchestrator.chat('What have I written about SVJ?',context,state)
            self.assertEqual(answer['mode'],'local');self.assertIn('SVJ rollout',answer['answer'])
            graph=runtime.graph.snapshot()
            self.assertTrue(graph['nodes']);self.assertTrue(runtime.health()['ok'])
            settings=runtime.settings_status();by_name={item['name']:item for item in settings['integrations']}
            self.assertEqual(by_name['OPENAI / ASTRA']['status'],'ACTION REQUIRED')
            self.assertEqual(by_name['GMAIL']['status'],'ACTION REQUIRED')
            self.assertEqual(by_name['CALENDAR']['status'],'ACTION REQUIRED')
            self.assertEqual(by_name['TELEGRAM']['status'],'DISABLED')
            self.assertEqual(by_name['SCREEN']['status'],'ACTION REQUIRED')
            with self.assertRaisesRegex(ValueError,'Gmail is not connected'):runtime.gmail.list_messages()
            with self.assertRaisesRegex(ValueError,'Google Calendar is not connected'):runtime.calendar.today()
            runtime.gmail.transport.assert_not_called();runtime.calendar.transport.assert_not_called()

    def test_missing_hardware_is_not_a_startup_dependency(self):
        with patch.dict(os.environ,{'JARVIS_DATA_DIR':str(self.root/'data'),'OPENAI_API_KEY':'','JARVIS_EMBEDDINGS':''}):
            runtime=Runtime(self.root,lambda:str(self.notes))
        health=runtime.health()
        self.assertFalse(health['camera_required']);self.assertFalse(health['microphone_required'])
        self.assertEqual(runtime.focus.status()['state'],'IDLE')
        self.assertFalse(runtime.vision.enabled)


if __name__=='__main__':unittest.main()
