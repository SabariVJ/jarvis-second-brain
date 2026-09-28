from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path

from jarvis.automations import AutomationEngine
from jarvis.memory.database import Database
from jarvis.provider_events import ProviderEventSources


class Clock:
    def __init__(self): self.value = datetime(2026, 9, 28, 9, 0, tzinfo=timezone.utc)
    def __call__(self): return self.value
    def advance(self, seconds): self.value += timedelta(seconds=seconds)


class Briefing:
    def run(self): return {'spoken': 'Local briefing'}


class Focus:
    def status(self): return {'state': 'IDLE'}


class Gmail:
    def __init__(self, connected=True): self.connected=connected;self.items=[];self.calls=0
    def automation_candidates(self, limit=50):
        self.calls+=1
        if not self.connected: raise AssertionError('Unconfigured Gmail must remain inert')
        return self.items[:limit]


class Calendar:
    def __init__(self, connected=True): self.connected=connected;self.items=[];self.calls=[]
    def events(self, start, end, query='', limit=250):
        self.calls.append((start,end,query,limit))
        if not self.connected: raise AssertionError('Unconfigured Calendar must remain inert')
        return {'items':self.items[:limit]}


def provider_rule(provider, event, conditions=None, name='Provider reminder'):
    return {'name':name,'trigger':{'type':'PROVIDER_EVENT','provider':provider,'event':event},
        'conditions':conditions or {},
        'action':{'type':'LOCAL_NOTIFICATION','title':'Provider notice','message':'Review the item locally.'},
        'enabled':True}


class ProviderEventSourceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.db=Database(Path(self.tmp.name)/'memory.sqlite')
        self.clock=Clock();self.gmail=Gmail();self.calendar=Calendar()
        self.engine=AutomationEngine(self.db,Briefing(),Focus(),self.clock)
        self.sources=ProviderEventSources(self.db,self.gmail,self.calendar,self.engine,self.clock)

    def test_sources_start_disabled_and_unconfigured_enablement_is_inert(self):
        self.engine.create(provider_rule('GMAIL','IMPORTANT_EMAIL',{'importance':'IMPORTANT'}))
        self.assertEqual(self.sources.status()['GMAIL']['status'],'DISABLED')
        self.assertEqual(self.sources.run_due()['polled'],[])
        self.assertEqual(self.gmail.calls,0)
        self.gmail.connected=False
        state=self.sources.configure('GMAIL',True)
        self.assertTrue(state['enabled']);self.assertEqual(state['status'],'NOT CONNECTED')
        self.assertEqual(self.sources.run_due()['polled'],['GMAIL'])
        self.assertEqual(self.sources.status()['GMAIL']['status'],'NOT CONNECTED')
        self.assertEqual(self.gmail.calls,0)
        self.sources.configure('GMAIL',False)
        self.assertEqual(self.sources.status()['GMAIL']['status'],'DISABLED')

    def test_gmail_baseline_new_important_message_dedup_and_restart_provenance(self):
        self.engine.create(provider_rule('GMAIL','IMPORTANT_EMAIL',{'importance':'IMPORTANT'},'Important mail'))
        self.gmail.items=[{'id':'old-message','importance':'IMPORTANT'}]
        self.sources.configure('GMAIL',True)
        self.sources.run_due()  # First check records a baseline without notifications.
        self.assertEqual(self.engine.list()['notifications'],[])
        self.gmail.items.append({'id':'new-message','importance':'IMPORTANT'})
        self.clock.advance(300);self.sources.run_due()
        notifications=self.engine.list()['notifications']
        self.assertEqual(len(notifications),1)
        source=notifications[0]['source']
        self.assertEqual(source['provider'],'GMAIL');self.assertEqual(source['event'],'IMPORTANT_EMAIL')
        self.assertRegex(source['source_id'],r'^[0-9a-f]{64}$')
        stored=str(self.engine.list()['runs'])
        self.assertIn(source['source_id'],stored);self.assertNotIn('new-message',stored)
        self.assertNotIn('subject',stored);self.assertNotIn('body',stored)

        restarted_engine=AutomationEngine(self.db,Briefing(),Focus(),self.clock)
        restarted=ProviderEventSources(self.db,self.gmail,self.calendar,restarted_engine,self.clock)
        self.clock.advance(300);restarted.run_due()
        self.assertEqual(restarted_engine.list()['notifications'],[])
        self.assertEqual(len(restarted_engine.list()['runs']),1)
        self.assertTrue(restarted.status()['GMAIL']['enabled'])

    def test_calendar_threshold_baseline_and_event_fires_once_without_mutation(self):
        self.engine.create(provider_rule('CALENDAR','CALENDAR_APPROACHING',
            {'minutes_before':30},'Calendar in thirty minutes'))
        self.sources.configure('CALENDAR',True)
        self.sources.run_due()  # Empty first poll establishes the baseline.
        event_start=(self.clock.value+timedelta(minutes=15)).isoformat()
        self.calendar.items=[{'id':'evt-1','summary':'Private event title','start':event_start,
                              'status':'confirmed','location':'Private location'}]
        self.clock.advance(300);self.sources.run_due()
        notifications=self.engine.list()['notifications']
        self.assertEqual(len(notifications),1)
        source=notifications[0]['source']
        self.assertEqual(source['provider'],'CALENDAR')
        self.assertEqual(source['event'],'CALENDAR_APPROACHING')
        self.assertRegex(source['source_id'],r'^[0-9a-f]{64}$')
        self.assertNotIn('Private event title',str(self.engine.list()))
        self.assertNotIn('Private location',str(self.engine.list()))
        self.assertEqual(len(self.calendar.calls),2)
        self.assertTrue(all(call[2]=='' and call[3]==250 for call in self.calendar.calls))
        self.assertFalse(any(hasattr(self.calendar,name) for name in ('create','reschedule','cancel')))

        self.clock.advance(300);self.sources.run_due()
        self.assertEqual(len(self.engine.list()['notifications']),1)
        self.assertEqual(len(self.engine.list()['runs']),1)
        restarted_engine=AutomationEngine(self.db,Briefing(),Focus(),self.clock)
        restarted=ProviderEventSources(self.db,self.gmail,self.calendar,restarted_engine,self.clock)
        self.clock.advance(300);restarted.run_due()
        self.assertEqual(len(restarted_engine.list()['runs']),1)

    def test_calendar_waits_until_rule_lead_time_and_baselines_already_due_events(self):
        self.engine.create(provider_rule('CALENDAR','CALENDAR_APPROACHING',
            {'minutes_before':15},'Calendar in fifteen minutes'))
        self.sources.configure('CALENDAR',True)
        self.calendar.items=[{'id':'evt-old','start':(self.clock.value+timedelta(minutes=10)).isoformat()}]
        self.sources.run_due()
        self.assertEqual(self.engine.list()['notifications'],[])
        self.calendar.items=[{'id':'evt-new','start':(self.clock.value+timedelta(minutes=25)).isoformat()}]
        self.clock.advance(300);self.sources.run_due()
        self.assertEqual(len(self.engine.list()['notifications']),0)
        self.clock.advance(360);self.calendar.items[0]['start']=(self.clock.value+timedelta(minutes=14)).isoformat()
        self.sources.run_due()
        self.assertEqual(len(self.engine.list()['notifications']),1)

    def test_provider_failure_is_redacted_and_does_not_block_local_events(self):
        self.engine.create(provider_rule('GMAIL','IMPORTANT_EMAIL',{'importance':'IMPORTANT'}))
        self.sources.configure('GMAIL',True)
        self.gmail.automation_candidates=lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError('private provider payload and token=secret-value'))
        self.sources.run_due()
        status=self.sources.status()['GMAIL']
        self.assertEqual(status['status'],'ERROR')
        self.assertNotIn('secret-value',str(status));self.assertNotIn('private provider payload',str(status))
        self.assertIn('available',status['error'])
        local=self.engine.create({'name':'Build','trigger':{'type':'EVENT','event':'BUILD_FINISHED'},
            'conditions':{},'action':{'type':'LOCAL_NOTIFICATION','title':'Done','message':'Build finished.'},'enabled':True})
        self.assertTrue(local['enabled'])
        self.assertEqual(len(self.engine.emit_event('BUILD_FINISHED')['runs']),1)

    def test_calendar_failure_isolated_from_local_automation(self):
        self.engine.create(provider_rule('CALENDAR','CALENDAR_APPROACHING',{'minutes_before':30}))
        self.sources.configure('CALENDAR',True)
        self.calendar.events=lambda *args,**kwargs: (_ for _ in ()).throw(
            RuntimeError('private calendar title and bearer token-value'))
        self.sources.run_due()
        status=self.sources.status()['CALENDAR']
        self.assertEqual(status['status'],'ERROR')
        self.assertNotIn('private calendar title',str(status));self.assertNotIn('token-value',str(status))
        self.assertEqual(len(self.engine.emit_event('FOCUS_STARTED')['runs']),0)

    def test_provider_emission_deduplicates_and_cannot_expand_permissions(self):
        rule=self.engine.create(provider_rule('GMAIL','IMPORTANT_EMAIL',{'importance':'IMPORTANT'}))
        args={'importance':'IMPORTANT'}
        first=self.engine.emit_provider_event('GMAIL','IMPORTANT_EMAIL',args,'opaque-source', [rule['id']])
        second=self.engine.emit_provider_event('GMAIL','IMPORTANT_EMAIL',args,'opaque-source', [rule['id']])
        self.assertEqual(len(first['runs']),1);self.assertTrue(second['duplicate'])
        unsafe=provider_rule('GMAIL','IMPORTANT_EMAIL')
        unsafe['action']={'type':'SEND_EMAIL','to':'other@example.test'}
        with self.assertRaises(ValueError):self.engine.create(unsafe)
        with self.assertRaises(ValueError):self.engine.emit_provider_event(
            'CALENDAR','IMPORTANT_EMAIL',{},'source')
        with self.assertRaises(ValueError):self.engine.emit_provider_event(
            'GMAIL','IMPORTANT_EMAIL',{},'refresh token: local-value')

    def test_receipts_expire_and_are_pruned_even_when_sources_are_disabled(self):
        self.engine.record_provider_event_seen('GMAIL','IMPORTANT_EMAIL','source-a')
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM provider_event_receipts').fetchone()[0],1)
        self.clock.advance(90*86400+1)
        self.sources.run_due()
        with self.db.connect() as db:self.assertEqual(db.execute('SELECT count(*) FROM provider_event_receipts').fetchone()[0],0)


if __name__=='__main__': unittest.main()
