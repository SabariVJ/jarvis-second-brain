import unittest
from datetime import datetime, timedelta, timezone

from jarvis.integrations.calendar import CalendarAdapter


class OAuth:
    configured=True
    def access_token(self):return 'mock-token'


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.calls=[]
        def transport(method,url,token,payload=None):
            self.calls.append((method,url,token,payload))
            if method=='GET':return {'items':[{'id':'evt1','summary':'Planning','start':{'dateTime':'2026-09-27T10:00:00+05:30'},'end':{'dateTime':'2026-09-27T11:00:00+05:30'}}]}
            if method=='POST' and url.endswith('/freeBusy'):
                return {'calendars':{'primary':{'busy':[{'start':'2026-09-27T10:00:00Z','end':'2026-09-27T11:00:00Z'}]}}}
            if method=='POST':return {'id':'evt-new','summary':payload.get('summary'),'start':payload.get('start',{}),'end':payload.get('end',{})}
            if method=='PATCH':return {'id':'evt1','summary':'Planning moved','start':payload['start'],'end':payload['end']}
            return {}
        local=timezone(timedelta(hours=5,minutes=30))
        self.adapter=CalendarAdapter(OAuth(),transport,lambda:datetime(2026,9,27,9,0,tzinfo=local))

    def test_status_and_disconnected_state(self):
        self.assertEqual(self.adapter.status()['state'],'CONFIGURED')
        adapter=CalendarAdapter(type('NoAuth',(),{'configured':False})())
        self.assertEqual(adapter.status()['state'],'NOT CONNECTED')
        with self.assertRaisesRegex(ValueError,'not connected'):adapter.today()

    def test_today_tomorrow_range_and_search(self):
        self.adapter.today();self.adapter.tomorrow()
        self.assertIn('2026-09-27T00%3A00%3A00%2B05%3A30',self.calls[0][1])
        self.assertIn('2026-09-28T00%3A00%3A00%2B05%3A30',self.calls[1][1])
        result=self.adapter.events('2026-09-27T00:00:00+05:30','2026-09-28T00:00:00+05:30','planning')
        self.assertEqual(result['items'][0]['id'],'evt1')
        self.assertIn('q=planning',self.calls[-1][1])

    def test_availability_returns_busy_periods(self):
        result=self.adapter.availability('2026-09-27T09:00:00Z','2026-09-27T12:00:00Z')
        self.assertEqual(len(result['busy']),1)
        self.assertEqual(self.calls[-1][0],'POST')
        self.assertTrue(self.calls[-1][1].endswith('/freeBusy'))

    def test_write_calls_require_confirmation(self):
        start='2026-09-27T12:00:00+05:30';end='2026-09-27T13:00:00+05:30'
        with self.assertRaises(PermissionError):self.adapter.create('Review',start,end,'yes')
        with self.assertRaises(PermissionError):self.adapter.reschedule('evt1',start,end,'yes')
        with self.assertRaises(PermissionError):self.adapter.cancel('evt1','yes')
        self.assertEqual(self.calls,[])

    def test_create_reschedule_cancel_report_provider_confirmations(self):
        start='2026-09-27T12:00:00+05:30';end='2026-09-27T13:00:00+05:30'
        created=self.adapter.create('Review',start,end,'CREATE Review','Agenda')
        self.assertTrue(created['confirmed']);self.assertEqual(created['id'],'evt-new')
        moved=self.adapter.reschedule('evt1',start,end,'RESCHEDULE evt1')
        self.assertTrue(moved['confirmed']);self.assertEqual(moved['id'],'evt1')
        canceled=self.adapter.cancel('evt1','CANCEL evt1')
        self.assertTrue(canceled['confirmed']);self.assertEqual(canceled['status'],'cancelled')
        self.assertEqual([c[0] for c in self.calls],['POST','PATCH','DELETE'])

    def test_invalid_ranges_and_text_are_rejected(self):
        with self.assertRaisesRegex(ValueError,'timezone'):
            self.adapter.events('2026-09-27T00:00:00','2026-09-28T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'after'):
            self.adapter.events('2026-09-28T00:00:00Z','2026-09-27T00:00:00Z')
        with self.assertRaisesRegex(ValueError,'title'):
            self.adapter.create('bad\ntitle','2026-09-27T12:00:00Z','2026-09-27T13:00:00Z','CREATE bad')


if __name__=='__main__':unittest.main()
