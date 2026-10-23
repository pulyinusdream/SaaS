from contextlib import closing
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
import sqlite3
import unittest
from unittest.mock import patch
from flask import request

from kjancy import create_app
import test_app as existing
from test_app import database


class Forms(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.forms, self.current = [], None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'form':
            self.current = {'action':attrs.get('action',''), 'controls':[]}
            self.forms.append(self.current)
        elif self.current is not None and tag in {'input','select','textarea'}:
            self.current['controls'].append(attrs.get('name'))

    def handle_endtag(self, tag):
        if tag == 'form': self.current = None

    def action_for(self, control, fallback):
        return next(form['action'] or fallback for form in self.forms if control in form['controls'])


class Followups(unittest.TestCase):
    setUp = existing.AccountsAndLeads.setUp
    tearDown = existing.AccountsAndLeads.tearDown
    csrf = existing.AccountsAndLeads.csrf
    register = existing.AccountsAndLeads.register
    inquiry = existing.AccountsAndLeads.inquiry

    def fixture(self):
        self.workspace, public = self.register()
        self.lead = self.inquiry(public)
        self.path = f'/leads/{self.lead}/follow-up'
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            self.owner = db.execute('SELECT id FROM users').fetchone()[0]
        return self.workspace

    def row(self):
        with closing(sqlite3.connect(Path(self.temp.name) / 'kjancy.sqlite3')) as db:
            db.row_factory = sqlite3.Row
            return dict(db.execute('SELECT * FROM leads WHERE id=?', (self.lead,)).fetchone())

    def save(self, **changes):
        values = {'csrf_token': self.csrf(self.client, f'/leads/{self.lead}'), 'version': str(self.row()['version']),
                  'operation': 'save', 'assigned_user_id': self.owner, 'followup_action': 'Call about the repair',
                  'followup_due': '2026-10-24T10:00', 'workspace_timezone': 'UTC'}
        values.update(changes)
        return self.client.post(self.path, data=values)

    def test_assignment_and_due_time_persist_with_activity(self):
        self.fixture()
        self.assertEqual(self.save().status_code, 303)
        row = self.row()
        self.assertEqual(row['assigned_user_id'], self.owner)
        self.assertEqual(row['followup_action'], 'Call about the repair')
        self.assertEqual(row['followup_due'], 1792836000)
        self.assertIsNone(row['followup_completed_at'])
        page = self.client.get(f'/leads/{self.lead}')
        self.assertIn(b'Call about the repair', page.data)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            descriptions = [r[0] for r in db.execute('SELECT description FROM lead_events')]
        self.assertTrue(any('Assigned to Jordan Reed' in value for value in descriptions))
        self.assertTrue(any('Follow-up scheduled' in value for value in descriptions))

    def test_completion_requires_outcome_and_reschedule_returns_to_pending(self):
        self.fixture()
        self.assertEqual(self.save().status_code, 303)
        self.assertEqual(self.save(operation='complete', followup_outcome='').status_code, 422)
        self.assertIsNone(self.row()['followup_completed_at'])
        self.assertEqual(self.save(operation='complete', followup_outcome='Customer asked for an estimate.').status_code, 303)
        self.assertIsNotNone(self.row()['followup_completed_at'])
        self.assertEqual(self.row()['followup_outcome'], 'Customer asked for an estimate.')
        self.assertEqual(self.save(followup_action='Send estimate', followup_due='2026-10-25T11:00').status_code, 303)
        self.assertIsNone(self.row()['followup_completed_at'])
        self.assertEqual(self.row()['followup_outcome'], '')
        self.assertIn(b'Customer asked for an estimate.', self.client.get(f'/leads/{self.lead}').data)

    def test_invalid_partial_and_oversized_followups_do_not_write(self):
        self.fixture()
        for changes in ({'followup_action':''}, {'followup_due':''}, {'followup_due':'not-a-date'},
                        {'followup_due':'9999-01-01T10:00'}, {'followup_action':'a' * 241},
                        {'operation':'complete', 'followup_outcome':'Cannot complete a missing follow-up'},
                        {'operation':'unknown'}, {'version':'9' * 100}):
            before = self.row()
            response = self.save(**changes)
            self.assertIn(response.status_code, (409, 422), changes)
            self.assertEqual(self.row(), before)

    def test_foreign_member_lead_and_csrf_are_rejected(self):
        self.fixture()
        other = self.app.test_client()
        self.register(other, 'other@harbor.test', 'Harbor Electric')
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            foreign = db.execute("SELECT id FROM users WHERE email='other@harbor.test'").fetchone()[0]
        self.assertEqual(self.save(assigned_user_id=foreign).status_code, 422)
        self.assertEqual(self.save(csrf_token='forged').status_code, 400)
        response = other.post(self.path, data={'csrf_token':self.csrf(other, '/inbox'), 'operation':'save', 'version':'1'})
        self.assertEqual(response.status_code, 404)
        self.assertIsNone(self.row()['assigned_user_id'])

    def test_stale_followup_cannot_overwrite_status_or_completion(self):
        self.fixture()
        self.assertEqual(self.save().status_code, 303)
        version = self.row()['version']
        response = self.client.post(f'/leads/{self.lead}', data={'csrf_token':self.csrf(self.client, f'/leads/{self.lead}'), 'version':str(version), 'status':'Contacted', 'internal_notes':'Spoke with customer'})
        self.assertEqual(response.status_code, 303)
        before = self.row()
        self.assertEqual(self.save(version=str(version), followup_action='Stale update').status_code, 409)
        self.assertEqual(self.row(), before)
        self.assertEqual(self.save(operation='complete', followup_outcome='Called').status_code, 303)
        before = self.row()
        self.assertEqual(self.save(version=str(before['version'] - 1), operation='complete', followup_outcome='Old completion').status_code, 409)
        self.assertEqual(self.row(), before)

    def test_removed_dispatcher_is_unassigned_and_stale_assignment_fails(self):
        self.fixture()
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            db.execute("INSERT INTO users(id,name,email,password_hash,created) VALUES('dispatcher','Casey','casey@example.test','hash',1)")
            db.execute("INSERT INTO memberships VALUES(?, 'dispatcher', 'dispatcher')", (self.workspace,))
        self.assertEqual(self.save(assigned_user_id='dispatcher').status_code, 303)
        version = self.row()['version']
        response = self.client.post('/team/members/dispatcher/remove', data={'csrf_token':self.csrf(self.client, '/team')})
        self.assertEqual(response.status_code, 303)
        self.assertIsNone(self.row()['assigned_user_id'])
        self.assertGreater(self.row()['version'], version)
        self.assertEqual(self.save(assigned_user_id='dispatcher').status_code, 422)
        self.assertIn(b'Unassigned', self.client.get(f'/leads/{self.lead}').data)

    def set_timezone(self, zone, client=None):
        client = client or self.client
        return client.post('/workspace/timezone', data={'csrf_token':self.csrf(client, '/inbox'), 'timezone':zone})

    def test_workspace_timezone_is_owner_controlled_and_stale_zone_rejected(self):
        self.fixture()
        self.assertEqual(self.set_timezone('Asia/Singapore').status_code, 303)
        self.assertEqual(self.save(workspace_timezone='UTC').status_code, 409)
        self.assertEqual(self.save(workspace_timezone='Asia/Singapore').status_code, 303)
        self.assertEqual(self.row()['followup_due'], 1792807200)
        self.assertEqual(self.set_timezone('../private').status_code, 422)
        self.assertIn(b'Asia/Singapore', self.client.get('/inbox').data)

    def test_dst_gap_and_repeated_local_time_are_not_silently_shifted(self):
        self.fixture()
        self.assertEqual(self.set_timezone('America/New_York').status_code, 303)
        for due in ('2026-03-08T02:30', '2026-11-01T01:30'):
            self.assertEqual(self.save(workspace_timezone='America/New_York', followup_due=due).status_code, 422)
        self.assertEqual(self.save(workspace_timezone='America/New_York', followup_due='2026-11-01T03:00').status_code, 303)
        self.assertEqual(self.row()['followup_due'], 1793520000)

    def test_daily_queues_use_workspace_day_and_exclude_completed_closed_and_other_companies(self):
        self.fixture()
        self.set_timezone('Asia/Singapore')
        self.assertEqual(self.save(workspace_timezone='Asia/Singapore', followup_due='2026-10-24T00:30').status_code, 303)
        # 16:15 UTC is already October 24 in Singapore; this lead is due later today.
        with patch('kjancy.followups.utc_now', return_value=datetime(2026,10,23,16,15,tzinfo=timezone.utc)):
            self.assertIn(b'Taylor Morgan', self.client.get('/inbox?view=today').data)
            self.assertNotIn(b'Taylor Morgan', self.client.get('/inbox?view=overdue').data)
            self.assertIn(b'Taylor Morgan', self.client.get('/inbox?view=mine').data)
            self.assertNotIn(b'Taylor Morgan', self.client.get('/inbox?view=unassigned').data)
        with patch('kjancy.followups.utc_now', return_value=datetime(2026,10,23,17,tzinfo=timezone.utc)):
            self.assertIn(b'Taylor Morgan', self.client.get('/inbox?view=overdue').data)
        self.assertEqual(self.save(operation='complete', followup_outcome='Finished').status_code, 303)
        self.assertNotIn(b'Taylor Morgan', self.client.get('/inbox?view=overdue').data)
        self.assertEqual(self.save(workspace_timezone='Asia/Singapore', followup_due='2020-01-01T10:00').status_code, 303)
        self.client.post(f'/leads/{self.lead}', data={'csrf_token':self.csrf(self.client, f'/leads/{self.lead}'), 'version':str(self.row()['version']), 'status':'Closed'})
        self.assertNotIn(b'Taylor Morgan', self.client.get('/inbox?view=overdue').data)
        other = self.app.test_client()
        self.register(other, 'owner@harbor.test', 'Harbor Electric')
        for view in ('today','overdue','mine','unassigned'):
            self.assertNotIn(b'Taylor Morgan', other.get('/inbox?view=' + view).data)
        self.assertEqual(self.client.get('/inbox?view=invalid').status_code, 400)

    def test_existing_leads_and_status_writes_preserve_handoff_across_restart(self):
        self.fixture()
        before = self.row()
        self.assertIn('assigned_user_id', before)
        self.assertIsNone(before['assigned_user_id'])
        self.assertEqual(self.save().status_code, 303)
        create_app({'TESTING':True, 'DATA_DIR':self.temp.name, 'SECRET_KEY':'test-signing-key'})
        self.assertEqual(self.row()['followup_action'], 'Call about the repair')
        response = self.client.post(f'/leads/{self.lead}', data={'csrf_token':self.csrf(self.client, f'/leads/{self.lead}'), 'version':str(self.row()['version']), 'status':'Contacted', 'internal_notes':'Existing form stays supported'})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(self.row()['followup_action'], 'Call about the repair')

    def test_removed_actor_cannot_finish_a_write_after_identity_was_loaded(self):
        active = {'enabled':False}
        @self.app.before_request
        def remove_during_request():
            if active['enabled'] and request.method == 'POST' and request.path.startswith('/leads/'):
                with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
                    db.execute('DELETE FROM memberships WHERE workspace_id=? AND user_id=?', (self.workspace, active['user']))
        self.fixture()
        self.assertEqual(self.save().status_code, 303)
        dispatcher = self.app.test_client()
        self.register(dispatcher, 'dispatcher@example.test', 'Dispatcher other business')
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            active['user'] = db.execute("SELECT id FROM users WHERE email='dispatcher@example.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')", (self.workspace,active['user']))
        dispatcher.post('/workspace/switch', data={'csrf_token':self.csrf(dispatcher, '/inbox'), 'workspace_id':self.workspace})
        for operation in ('save','complete','status'):
            with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
                db.execute("INSERT OR IGNORE INTO memberships VALUES(?,?,'dispatcher')", (self.workspace,active['user']))
            token = self.csrf(dispatcher, f'/leads/{self.lead}')
            before = self.row()
            active['enabled'] = True
            payload = {'csrf_token':token,'version':str(before['version']),'operation':operation,'assigned_user_id':self.owner,
                       'followup_action':'Write after removal','followup_due':'2026-10-24T10:00','workspace_timezone':'UTC',
                       'followup_outcome':'Unauthorized completion','status':'Closed','internal_notes':'Unauthorized note'}
            endpoint = f'/leads/{self.lead}' if operation=='status' else self.path
            response = dispatcher.post(endpoint,data=payload)
            active['enabled'] = False
            with self.subTest(operation=operation):
                self.assertEqual(response.status_code,404,operation)
                self.assertEqual(self.row(),before,operation)

    def test_assignment_preserves_existing_instant_in_a_repeated_hour(self):
        self.fixture()
        self.assertEqual(self.save(followup_due='2026-11-01T05:30').status_code,303)
        original = self.row()['followup_due']
        self.assertEqual(self.set_timezone('America/New_York').status_code,303)
        self.assertEqual(self.save(assigned_user_id='',workspace_timezone='America/New_York',followup_due='2026-11-01T01:30').status_code,303)
        self.assertIsNone(self.row()['assigned_user_id'])
        self.assertEqual(self.row()['followup_due'],original)

    def test_today_uses_23_and_25_hour_calendar_days(self):
        self.fixture()
        self.set_timezone('America/New_York')
        for clock,inside,outside in (
            (datetime(2026,3,8,16,tzinfo=timezone.utc),datetime(2026,3,9,3,30,tzinfo=timezone.utc),datetime(2026,3,9,4,tzinfo=timezone.utc)),
            (datetime(2026,11,1,16,tzinfo=timezone.utc),datetime(2026,11,2,4,30,tzinfo=timezone.utc),datetime(2026,11,2,5,tzinfo=timezone.utc)),
        ):
            with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
                db.execute("UPDATE leads SET followup_action='Day boundary',followup_due=? WHERE id=?",(int(inside.timestamp()),self.lead))
            with patch('kjancy.followups.utc_now',return_value=clock):
                self.assertIn(b'Taylor Morgan',self.client.get('/inbox?view=today').data)
            with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
                db.execute('UPDATE leads SET followup_due=? WHERE id=?',(int(outside.timestamp()),self.lead))
            with patch('kjancy.followups.utc_now',return_value=clock):
                self.assertNotIn(b'Taylor Morgan',self.client.get('/inbox?view=today').data)

    def test_status_form_still_saves_after_a_followup_validation_error(self):
        self.fixture()
        response = self.save(followup_action='')
        self.assertEqual(response.status_code,422)
        action = Forms(response.get_data(as_text=True)).action_for('status',response.request.path)
        result = self.client.post(action,data={'csrf_token':self.csrf(self.client,f'/leads/{self.lead}'),'version':str(self.row()['version']),'status':'Contacted','internal_notes':'Called'})
        self.assertEqual(result.status_code,303)
        self.assertEqual(self.row()['status'],'Contacted')

    def test_search_form_still_works_after_a_timezone_validation_error(self):
        self.fixture()
        response = self.set_timezone('../private')
        self.assertEqual(response.status_code,422)
        action = Forms(response.get_data(as_text=True)).action_for('q',response.request.path)
        result = self.client.get(action,query_string={'q':'Taylor','view':'all'})
        self.assertEqual(result.status_code,200)
        self.assertIn(b'Taylor Morgan',result.data)

    def test_legacy_schema_migrates_without_changing_original_values(self):
        legacy = Path(self.temp.name) / 'legacy'
        legacy.mkdir()
        with closing(sqlite3.connect(legacy / 'kjancy.sqlite3')) as db, db:
            db.executescript((Path(__file__).resolve().parents[1] / 'kjancy/schema.sql').read_text())
            db.execute("INSERT INTO users VALUES('old-user','Existing owner','old@example.test','existing-hash',123)")
            db.execute("INSERT INTO workspaces VALUES('old-workspace','Existing business','existing-public',123)")
            db.execute("INSERT INTO memberships VALUES('old-workspace','old-user','owner')")
            db.execute("INSERT INTO leads(id,workspace_id,customer_name,email,service,location,internal_notes,created,updated) VALUES('old-lead','old-workspace','Existing customer','customer@example.test','HVAC','Austin','Existing notes',123,123)")
        create_app({'TESTING':True,'DATA_DIR':str(legacy),'SECRET_KEY':'test-signing-key'})
        with closing(sqlite3.connect(legacy / 'kjancy.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT customer_name,internal_notes,created,assigned_user_id,followup_action,followup_due FROM leads').fetchone(),('Existing customer','Existing notes',123,None,'',None))
            self.assertEqual(db.execute('SELECT name,public_id,timezone FROM workspaces').fetchone(),('Existing business','existing-public','UTC'))
            self.assertEqual(db.execute('SELECT password_hash FROM users').fetchone()[0],'existing-hash')

    def test_dispatcher_can_manage_handoffs_but_cannot_change_workspace_timezone(self):
        self.fixture()
        dispatcher = self.app.test_client()
        self.register(dispatcher,'dispatcher@example.test','Dispatcher other business')
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            user = db.execute("SELECT id FROM users WHERE email='dispatcher@example.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')",(self.workspace,user))
        dispatcher.post('/workspace/switch',data={'csrf_token':self.csrf(dispatcher,'/inbox'),'workspace_id':self.workspace})
        token = self.csrf(dispatcher,f'/leads/{self.lead}')
        response = dispatcher.post(self.path,data={'csrf_token':token,'version':'1','operation':'save','assigned_user_id':user,'followup_action':'Call customer','followup_due':'2026-10-24T09:00','workspace_timezone':'UTC'})
        self.assertEqual(response.status_code,303)
        self.assertEqual(self.row()['assigned_user_id'],user)
        self.assertEqual(self.set_timezone('Asia/Singapore',dispatcher).status_code,403)
        self.assertIn(b'Taylor Morgan',dispatcher.get('/inbox?view=mine').data)

