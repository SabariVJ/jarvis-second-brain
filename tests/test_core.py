import unittest
from jarvis.core.state import StateMachine
from jarvis.core.context import Sessions
from jarvis.security import local_request, redact

class CoreTests(unittest.TestCase):
    def test_state_paths(self):
        m = StateMachine()
        for s in ['WAKE_DETECTED','LISTENING','TRANSCRIBING','RETRIEVING','THINKING','WAITING_FOR_APPROVAL','TOOL_RUNNING','SPEAKING','INTERRUPTED','IDLE','OFFLINE','RETRIEVING','ERROR','IDLE']:
            m.transition(s)
        self.assertEqual(m.snapshot()['state'], 'IDLE')
        with self.assertRaises(ValueError): m.transition('TOOL_RUNNING')

    def test_context_isolation_expiry(self):
        sessions = Sessions()
        a, ca, _ = sessions.get(); b, cb, _ = sessions.get()
        ca.select('doc'); self.assertIsNone(cb.selection())
        ca.selected_at -= 1801; self.assertIsNone(ca.selection())
        with self.assertRaises(ValueError): sessions.get('invented')

    def test_http_trust(self):
        h = {'Host':'localhost:4890', 'Content-Type':'application/json'}
        self.assertTrue(local_request(h, 4890, True))
        for patch in [{'Host':'evil.test:4890'}, {'Origin':'https://evil.test'}, {'Sec-Fetch-Site':'cross-site'}, {'Content-Type':'text/plain'}]:
            self.assertFalse(local_request(h | patch, 4890, True))
        self.assertNotIn('sk-secret', redact('error sk-secret'))
