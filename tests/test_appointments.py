from contextlib import closing
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from threading import Barrier
import unittest
from flask import request

from kjancy import create_app
import test_app as existing
from test_app import database


class Appointments(unittest.TestCase):
    setUp = existing.AccountsAndLeads.setUp
    tearDown = existing.AccountsAndLeads.tearDown
    csrf = existing.AccountsAndLeads.csrf
    register = existing.AccountsAndLeads.register
    inquiry = existing.AccountsAndLeads.inquiry

    def fixture(self):
        self.workspace, self.public = self.register()
        self.lead = self.inquiry(self.public)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            self.owner = db.execute('SELECT id FROM users').fetchone()[0]

    def lead_row(self, lead=None):
        with closing(sqlite3.connect(Path(self.temp.name) / 'kjancy.sqlite3')) as db:
            db.row_factory = sqlite3.Row
            return dict(db.execute('SELECT * FROM leads WHERE id=?',(lead or self.lead,)).fetchone())

    def active(self, lead=None):
        with closing(sqlite3.connect(Path(self.temp.name) / 'kjancy.sqlite3')) as db:
            db.row_factory = sqlite3.Row
            row = db.execute("SELECT * FROM appointments WHERE lead_id=? AND state='scheduled'",(lead or self.lead,)).fetchone()
            return dict(row) if row else None

    def payload(self, lead=None, **changes):
        lead = lead or self.lead
        values = {'csrf_token':self.csrf(self.client,f'/leads/{lead}'),'version':str(self.lead_row(lead)['version']),
                  'operation':'save','appointment_id':'','assigned_user_id':self.owner,'start':'2026-10-24T10:00',
                  'duration_minutes':'60','workspace_timezone':'UTC'}
        values.update(changes)
        return values

    def book(self, lead=None, **changes):
        lead = lead or self.lead
        return self.client.post(f'/leads/{lead}/appointment',data=self.payload(lead,**changes))

    def status(self, status, version=None):
        return self.client.post(f'/leads/{self.lead}',data={'csrf_token':self.csrf(self.client,f'/leads/{self.lead}'),
            'version':str(version if version is not None else self.lead_row()['version']),'status':status,'internal_notes':'Existing notes'})

    def warning_token(self, response):
        match = re.search(rb'name="overlap_token" value="([^"]+)"',response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def test_scheduling_persists_actual_slot_and_updates_lead_atomically(self):
        self.fixture()
        self.assertEqual(self.client.get(f'/leads/{self.lead}/appointment').status_code,200)
        self.assertEqual(self.book().status_code,303)
        item = self.active()
        self.assertEqual((item['start_at'],item['end_at']),(1792836000,1792839600))
        self.assertEqual(item['assigned_user_id'],self.owner)
        self.assertEqual(self.lead_row()['status'],'Appointment booked')
        self.assertEqual(self.lead_row()['version'],2)
        self.assertIsNone(self.lead_row()['assigned_user_id'])
        self.assertIn(b'Appointment scheduled',self.client.get(f'/leads/{self.lead}').data)
        self.assertIn(b'Taylor Morgan',self.client.get('/calendar?view=day&date=2026-10-24').data)

    def test_reschedule_keeps_identity_and_rejects_old_form_and_duplicate_post(self):
        self.fixture()
        original_payload = self.payload()
        self.assertEqual(self.client.post(f'/leads/{self.lead}/appointment',data=original_payload).status_code,303)
        original = self.active()
        self.assertEqual(self.client.post(f'/leads/{self.lead}/appointment',data=original_payload).status_code,409)
        self.assertEqual(self.book(appointment_id=original['id'],start='2026-10-25T12:00',duration_minutes='90').status_code,303)
        self.assertEqual(self.active()['id'],original['id'])
        self.assertEqual(self.active()['end_at']-self.active()['start_at'],5400)
        self.assertEqual(self.book(appointment_id=original['id'],version='2',start='2026-10-26T12:00').status_code,409)
        self.assertIn(b'Appointment rescheduled',self.client.get(f'/leads/{self.lead}').data)

    def test_cancel_requires_reason_retains_history_and_can_schedule_again(self):
        self.fixture()
        self.assertEqual(self.book().status_code,303)
        uid = self.active()['id']
        self.assertEqual(self.book(operation='cancel',appointment_id=uid,cancellation_reason='').status_code,422)
        self.assertIsNotNone(self.active())
        self.assertEqual(self.book(operation='cancel',appointment_id=uid,cancellation_reason='Customer requested another day.').status_code,303)
        self.assertIsNone(self.active())
        self.assertEqual(self.lead_row()['status'],'Contacted')
        self.assertNotIn(b'Taylor Morgan',self.client.get('/calendar?view=day&date=2026-10-24').data)
        self.assertIn(b'Taylor Morgan',self.client.get('/calendar?view=day&date=2026-10-24&include_cancelled=1').data)
        self.assertEqual(self.book(start='2026-10-26T09:00').status_code,303)
        self.assertNotEqual(self.active()['id'],uid)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM appointments').fetchone()[0],2)

    def test_overlaps_warn_before_write_require_bound_acknowledgement_and_allow_touching_slots(self):
        self.fixture()
        self.assertEqual(self.book().status_code,303)
        second = self.inquiry(self.public,'Casey Blake')
        self.assertEqual(self.book(second,start='2026-10-24T11:00').status_code,303)
        third = self.inquiry(self.public,'Avery Quinn')
        warning = self.book(third,start='2026-10-24T10:30')
        self.assertEqual(warning.status_code,409)
        self.assertIsNone(self.active(third))
        self.assertEqual(self.lead_row(third)['status'],'New')
        token = self.warning_token(warning)
        self.assertEqual(self.book(third,start='2026-10-24T10:30',confirm_overlap='yes',overlap_token='tampered').status_code,409)
        self.assertEqual(self.book(third,start='2026-10-24T10:30',overlap_token=token).status_code,409)
        self.assertEqual(self.book(third,start='2026-10-24T10:30',confirm_overlap='yes',overlap_token=token).status_code,303)

    def test_conflict_changes_invalidate_old_acknowledgement(self):
        self.fixture()
        self.assertEqual(self.book().status_code,303)
        second = self.inquiry(self.public,'Casey Blake')
        warning = self.book(second,start='2026-10-24T10:30')
        self.assertEqual(warning.status_code,409)
        token = self.warning_token(warning)
        self.assertEqual(self.book(appointment_id=self.active()['id'],start='2026-10-24T09:45',duration_minutes='120').status_code,303)
        result = self.book(second,start='2026-10-24T10:30',confirm_overlap='yes',overlap_token=token)
        self.assertEqual(result.status_code,409)
        self.assertIsNone(self.active(second))
        self.assertEqual(self.book(second,start='2026-10-24T10:30',confirm_overlap='yes',overlap_token=self.warning_token(result)).status_code,303)

    def test_corrected_free_slot_saves_without_acknowledging_old_conflicts(self):
        self.fixture()
        self.assertEqual(self.book().status_code,303)
        second = self.inquiry(self.public,'Casey Blake')
        warning = self.book(second,start='2026-10-24T10:30')
        self.assertEqual(warning.status_code,409)
        self.assertEqual(self.book(second,start='2026-10-24T12:00',overlap_token=self.warning_token(warning)).status_code,303)
        self.assertEqual(self.active(second)['start_at'],1792843200)

    def test_simultaneous_bookings_serialize_and_warn_before_second_write(self):
        self.fixture()
        second = self.inquiry(self.public,'Casey Blake')
        clients = [self.app.test_client(),self.app.test_client()]
        cookie_name = self.app.config['SESSION_COOKIE_NAME']
        cookie = self.client.get_cookie(cookie_name)
        for client in clients:
            client.set_cookie(cookie_name,cookie.value)
        requests = [(clients[0],self.lead,self.payload()),(clients[1],second,self.payload(second))]
        barrier = Barrier(2)
        def submit(item):
            client,lead,payload = item
            barrier.wait(timeout=10)
            return client.post(f'/leads/{lead}/appointment',data=payload).status_code
        with ThreadPoolExecutor(max_workers=2) as workers:
            results = sorted(workers.map(submit,requests))
        self.assertEqual(results,[303,409])
        self.assertEqual(sum(self.active(lead) is not None for lead in (self.lead,second)),1)
        self.assertEqual(sorted(self.lead_row(lead)['version'] for lead in (self.lead,second)),[1,2])

    def test_invalid_slots_and_closed_leads_do_not_create_appointments(self):
        self.fixture()
        for changes in ({'start':''},{'start':'not-a-date'},{'duration_minutes':'0'},{'duration_minutes':'481'},
                        {'duration_minutes':'61'},{'duration_minutes':'a'},{'assigned_user_id':''},{'assigned_user_id':'foreign'},
                        {'operation':'unknown'},{'version':'9'*100}):
            with self.subTest(changes=changes):
                self.assertEqual(self.book(**changes).status_code,422)
                self.assertIsNone(self.active())
                self.assertEqual(self.lead_row()['status'],'New')
        self.assertEqual(self.status('Closed').status_code,303)
        self.assertEqual(self.book().status_code,422)
        self.assertIsNone(self.active())

    def test_tenant_scope_csrf_and_calendar_filters_do_not_leak_other_business(self):
        self.fixture()
        other = self.app.test_client()
        other_workspace,public = self.register(other,'other@harbor.test','Harbor Electric')
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            foreign = db.execute("SELECT id FROM users WHERE email='other@harbor.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')",(other_workspace,self.owner))
        other_lead = self.inquiry(public,'Other private customer')
        response = other.post(f'/leads/{other_lead}/appointment',data={'csrf_token':self.csrf(other,f'/leads/{other_lead}'), 'version':'1','operation':'save','appointment_id':'','assigned_user_id':self.owner,'start':'2026-10-24T10:00','duration_minutes':'60','workspace_timezone':'UTC'})
        self.assertEqual(response.status_code,303)
        self.assertEqual(self.book(assigned_user_id=foreign).status_code,422)
        self.assertEqual(self.book(csrf_token='forged').status_code,400)
        self.assertEqual(self.book(workspace_id=other_workspace).status_code,303)
        self.assertEqual(self.client.get(f'/leads/{other_lead}/appointment').status_code,404)
        self.assertEqual(other.post(f'/leads/{self.lead}/appointment',data={'csrf_token':self.csrf(other,'/inbox')}).status_code,404)
        self.assertNotIn(b'Other private customer',self.client.get('/calendar?view=week&date=2026-10-24&include_cancelled=1').data)
        self.assertEqual(self.client.get('/calendar?assignee='+foreign).status_code,400)

    def test_status_changes_cancel_only_after_a_successful_current_version_write(self):
        self.fixture()
        self.assertEqual(self.book().status_code,303)
        version = self.lead_row()['version']
        self.assertEqual(self.status('Contacted').status_code,422)
        self.assertEqual(self.lead_row()['status'],'Appointment booked')
        self.assertEqual(self.status('Appointment booked').status_code,303)
        self.assertEqual(self.status('Closed',version).status_code,409)
        self.assertIsNotNone(self.active())
        self.assertEqual(self.status('Closed').status_code,303)
        self.assertIsNone(self.active())
        self.assertEqual(self.lead_row()['status'],'Closed')
        self.assertIn(b'Lead closed',self.client.get(f'/leads/{self.lead}').data)

    def test_timezone_dst_and_unchanged_repeated_hour_preserve_instants(self):
        self.fixture()
        self.assertEqual(self.book(start='2026-11-01T05:30').status_code,303)
        original = self.active()
        self.client.post('/workspace/timezone',data={'csrf_token':self.csrf(self.client,'/inbox'),'timezone':'America/New_York'})
        self.assertEqual(self.book(appointment_id=original['id'],start='2026-11-01T01:30').status_code,409)
        self.assertEqual(self.book(appointment_id=original['id'],start='2026-11-01T01:30',workspace_timezone='America/New_York').status_code,303)
        self.assertEqual(self.active()['start_at'],original['start_at'])
        second = self.inquiry(self.public,'Casey Blake')
        for start in ('2026-03-08T02:30','2026-11-01T01:30'):
            self.assertEqual(self.book(second,start=start,workspace_timezone='America/New_York').status_code,422)
        self.assertIsNone(self.active(second))

    def test_calendar_includes_cross_midnight_and_25_hour_day_appointments(self):
        self.fixture()
        self.client.post('/workspace/timezone',data={'csrf_token':self.csrf(self.client,'/inbox'),'timezone':'Asia/Singapore'})
        self.assertEqual(self.book(start='2026-10-24T23:30',duration_minutes='120',workspace_timezone='Asia/Singapore').status_code,303)
        for day, expected in (('2026-10-23',False),('2026-10-24',True),('2026-10-25',True),('2026-10-26',False)):
            response = self.client.get('/calendar?view=day&date='+day)
            self.assertEqual(response.status_code,200)
            self.assertEqual(b'Taylor Morgan' in response.data,expected)
        self.assertIn(b'Taylor Morgan',self.client.get('/calendar?view=week&date=2026-10-25').data)
        self.client.post('/workspace/timezone',data={'csrf_token':self.csrf(self.client,'/inbox'),'timezone':'America/New_York'})
        self.assertEqual(self.book(appointment_id=self.active()['id'],start='2026-11-01T23:30',duration_minutes='30',workspace_timezone='America/New_York').status_code,303)
        self.assertIn(b'Taylor Morgan',self.client.get('/calendar?view=day&date=2026-11-01').data)
        self.assertNotIn(b'Taylor Morgan',self.client.get('/calendar?view=day&date=2026-11-02').data)
        for suffix in ('?view=bad','?date=not-a-date','?date=9999-01-01'):
            self.assertEqual(self.client.get('/calendar'+suffix).status_code,400)

    def test_member_removal_unassigns_appointment_and_invalidates_old_forms(self):
        self.fixture()
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            db.execute("INSERT INTO users(id,name,email,password_hash,created) VALUES('dispatcher','Sam','sam@example.test','hash',1)")
            db.execute("INSERT INTO memberships VALUES(?,'dispatcher','dispatcher')",(self.workspace,))
        self.assertEqual(self.book(assigned_user_id='dispatcher').status_code,303)
        before = self.lead_row()['version']
        uid = self.active()['id']
        self.client.post('/team/members/dispatcher/remove',data={'csrf_token':self.csrf(self.client,'/team')})
        self.assertIsNone(self.active()['assigned_user_id'])
        self.assertEqual(self.active()['state'],'scheduled')
        self.assertGreater(self.lead_row()['version'],before)
        self.assertEqual(self.book(appointment_id=uid,version=str(before)).status_code,409)
        self.assertIn(b'Taylor Morgan',self.client.get('/calendar?view=day&date=2026-10-24&assignee=unassigned').data)

    def test_revoked_actor_cannot_finish_schedule_or_cancel_after_identity_loading(self):
        flag = {'enabled':False}
        @self.app.before_request
        def revoke():
            if flag['enabled'] and request.method=='POST' and request.path.endswith('/appointment'):
                with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
                    db.execute('DELETE FROM memberships WHERE workspace_id=? AND user_id=?',(self.workspace,flag['user']))
        self.fixture()
        self.assertEqual(self.book().status_code,303)
        dispatcher = self.app.test_client()
        self.register(dispatcher,'dispatcher@example.test','Dispatcher business')
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            flag['user'] = db.execute("SELECT id FROM users WHERE email='dispatcher@example.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')",(self.workspace,flag['user']))
        dispatcher.post('/workspace/switch',data={'csrf_token':self.csrf(dispatcher,'/inbox'),'workspace_id':self.workspace})
        for operation in ('save','cancel'):
            with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
                db.execute("INSERT OR IGNORE INTO memberships VALUES(?,?,'dispatcher')",(self.workspace,flag['user']))
            payload = self.payload(appointment_id=self.active()['id'],operation=operation,cancellation_reason='Unauthorized cancellation')
            payload['csrf_token'] = self.csrf(dispatcher,f'/leads/{self.lead}')
            before = self.active()
            flag['enabled'] = True
            response = dispatcher.post(f'/leads/{self.lead}/appointment',data=payload)
            flag['enabled'] = False
            self.assertEqual(response.status_code,404)
            self.assertEqual(self.active(),before)

    def test_legacy_booked_status_is_preserved_without_inventing_appointment(self):
        self.fixture()
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            db.execute("UPDATE leads SET status='Appointment booked' WHERE id=?",(self.lead,))
        create_app({'TESTING':True,'DATA_DIR':self.temp.name,'SECRET_KEY':'test-signing-key'})
        self.assertIsNone(self.active())
        self.assertEqual(self.lead_row()['status'],'Appointment booked')
        self.assertIn(b'No calendar appointment',self.client.get(f'/leads/{self.lead}').data)

    def test_calendar_paginates_without_losing_filter_or_silently_hiding_records(self):
        self.fixture()
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            for index in range(51):
                uid = f'bulk-{index:02}'
                db.execute("INSERT INTO leads(id,workspace_id,customer_name,service,location,status,created,updated) VALUES(?,?,?,'HVAC','Austin','Appointment booked',1,1)",(uid,self.workspace,f'Customer {index:02}'))
                db.execute("INSERT INTO appointments(id,workspace_id,lead_id,assigned_user_id,start_at,end_at,state,created,updated) VALUES(?,?,?,?,?,?,'scheduled',1,1)",(uid,self.workspace,uid,self.owner,1792836000+index*60,1792836900+index*60))
        first = self.client.get('/calendar?view=day&date=2026-10-24&assignee=mine')
        self.assertIn(b'Customer 00',first.data)
        self.assertNotIn(b'Customer 50',first.data)
        second = self.client.get('/calendar?view=day&date=2026-10-24&assignee=mine&page=2')
        self.assertIn(b'Customer 50',second.data)
        self.assertNotIn(b'Customer 00',second.data)

    def test_online_backup_and_restore_keep_appointment_data(self):
        from kjancy.backup import create_backup, restore_backup
        self.fixture()
        self.assertEqual(self.book().status_code,303)
        archive = create_backup(self.temp.name,Path(self.temp.name)/'private-backups')
        restored = restore_backup(archive,Path(self.temp.name)/'recovered')
        with closing(sqlite3.connect(restored/'kjancy.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT start_at,end_at,state FROM appointments').fetchone(),(1792836000,1792839600,'scheduled'))
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
