from contextlib import closing
import json
from pathlib import Path
import sqlite3
import unittest
from urllib.parse import unquote, urlsplit
import re

from flask import request
from kjancy import create_app
import test_app as existing
from test_app import database


class BusinessSettings(unittest.TestCase):
    setUp = existing.AccountsAndLeads.setUp
    tearDown = existing.AccountsAndLeads.tearDown
    csrf = existing.AccountsAndLeads.csrf
    register = existing.AccountsAndLeads.register
    inquiry = existing.AccountsAndLeads.inquiry

    def fixture(self):
        self.workspace,self.public = self.register()
        self.assertEqual(self.client.get('/settings').status_code,200)

    def row(self,workspace=None):
        with closing(sqlite3.connect(Path(self.temp.name)/'kjancy.sqlite3')) as db:
            db.row_factory = sqlite3.Row
            return dict(db.execute('SELECT * FROM workspaces WHERE id=?',(workspace or self.workspace,)).fetchone())

    def payload(self,**changes):
        values = {'csrf_token':self.csrf(self.client,'/settings'),'settings_version':str(self.row()['settings_version']),
            'name':'Reed Cooling & Plumbing','contact_email':'hello@reed.test','contact_phone':'+1 555-010-2040',
            'services':'AC maintenance\nDrain cleaning','service_areas':'North Austin\nRound Rock','timezone':'Asia/Singapore'}
        values.update(changes)
        return values

    def save(self,**changes):
        return self.client.post('/settings',data=self.payload(**changes))

    def public_post(self,service='AC maintenance',client=None,**changes):
        client = client or self.app.test_client()
        data = {'csrf_token':self.csrf(client,f'/request/{self.public}'),'customer_name':'Casey Blake',
            'email':'casey@example.test','phone':'','service':service,'location':'A precise address outside listed areas',
            'message':'Please call before arriving.'}
        data.update(changes)
        return client.post(f'/request/{self.public}',data=data)

    def test_owner_settings_persist_and_feed_customer_and_manual_forms(self):
        self.fixture()
        self.assertEqual(self.save().status_code,303)
        row = self.row()
        self.assertEqual(row['name'],'Reed Cooling & Plumbing')
        self.assertEqual(json.loads(row['services_json']),['AC maintenance','Drain cleaning'])
        self.assertEqual(json.loads(row['service_areas_json']),['North Austin','Round Rock'])
        self.assertEqual((row['settings_version'],row['timezone']),(2,'Asia/Singapore'))
        public = self.app.test_client().get(f'/request/{self.public}')
        for value in (b'Reed Cooling &amp; Plumbing',b'hello@reed.test',b'North Austin',b'AC maintenance'):
            self.assertIn(value,public.data)
        self.assertNotIn(b'<option value="HVAC"',public.data)
        self.assertNotIn(b'owner@reed.test',public.data)
        manual = self.client.get('/leads/new')
        self.assertIn(b'<option value="Drain cleaning"',manual.data)
        self.assertEqual(self.public_post().status_code,303)
        self.assertIn(b'Casey Blake',self.client.get('/inbox').data)

    def test_default_services_survive_without_fabricated_setup(self):
        self.fixture()
        row = self.row()
        self.assertEqual((row['contact_email'],row['contact_phone'],row['services_json'],row['service_areas_json'],row['form_shared_at']),('','',None,'[]',None))
        page = self.client.get('/setup')
        self.assertIn(b'0 of 3 required steps complete',page.data)
        self.assertIn(b'<option value="HVAC"',self.app.test_client().get(f'/request/{self.public}').data)
        self.assertNotIn(b'Continue setup',self.client.get('/inbox').data)
        self.assertIn(b'Business setup',self.client.get('/settings').data)

    def test_invalid_settings_are_atomic_and_keep_submitted_values(self):
        self.fixture()
        before = self.row()
        for changes in ({'name':''},{'name':'x'*101},{'contact_email':'invalid'},
                        {'contact_email':'','contact_phone':''},{'contact_phone':'bad phone'},
                        {'services':''},{'services':'HVAC\nhvac'},{'services':'x'*61},
                        {'services':'\n'.join(f'Service {i}' for i in range(21))},
                        {'service_areas':''},{'service_areas':'x'*101},{'service_areas':'Austin\naustin'},
                        {'name':'Bad\nName'},{'services':'Bad\x00Service'},{'timezone':'../private'},
                        {'settings_version':'invalid'},{'settings_version':'9'*100}):
            with self.subTest(changes=changes):
                result = self.save(**changes)
                self.assertEqual(result.status_code,422)
                self.assertIn(b'data-error-summary',result.data)
                self.assertEqual(self.row(),before)
        self.assertEqual(self.save(contact_email='',contact_phone='555-010-2040').status_code,303)

    def test_stale_settings_and_timezone_writes_do_not_overwrite_each_other(self):
        self.fixture()
        old = self.payload()
        self.assertEqual(self.save().status_code,303)
        self.assertEqual(self.client.post('/settings',data=old).status_code,409)
        current = self.row()
        self.assertEqual(self.client.post('/workspace/timezone',data={'csrf_token':self.csrf(self.client,'/inbox'),
            'settings_version':'1','timezone':'UTC'}).status_code,409)
        self.assertEqual(self.row(),current)
        pending = self.payload()
        self.assertEqual(self.client.post('/workspace/timezone',data={'csrf_token':self.csrf(self.client,'/inbox'),
            'settings_version':'2','timezone':'America/New_York'}).status_code,303)
        self.assertEqual(self.client.post('/settings',data=pending).status_code,409)
        self.assertEqual(self.row()['timezone'],'America/New_York')

    def test_changes_preserve_old_lead_fields_and_reject_removed_service_on_new_requests(self):
        self.fixture()
        old_lead = self.inquiry(self.public)
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            before = db.execute('SELECT * FROM leads WHERE id=?',(old_lead,)).fetchone()
        self.assertEqual(self.save().status_code,303)
        result = self.public_post('HVAC')
        self.assertEqual(result.status_code,422)
        self.assertIn(b'Choose a service currently offered by this business',result.data)
        self.assertIn(b'Casey Blake',result.data)
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            self.assertEqual(db.execute('SELECT * FROM leads WHERE id=?',(old_lead,)).fetchone(),before)
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0],1)
        self.assertIn(b'HVAC',self.client.get(f'/leads/{old_lead}').data)
        self.assertEqual(self.client.post('/leads/new',data={'csrf_token':self.csrf(self.client,'/leads/new'),
            'customer_name':'Manual Customer','email':'manual@example.test','service':'Drain cleaning','location':'Austin'}).status_code,303)

    def test_settings_csrf_and_submitted_workspace_do_not_bypass_tenant_scope(self):
        self.fixture()
        other = self.app.test_client()
        foreign,_ = self.register(other,'other@harbor.test','Harbor Electric')
        self.assertEqual(self.save(csrf_token='forged').status_code,400)
        self.assertEqual(self.save(workspace_id=foreign).status_code,303)
        self.assertEqual(self.row(foreign)['name'],'Harbor Electric')
        self.assertNotIn(b'hello@reed.test',other.get('/settings').data)
        token = self.csrf(self.client,'/settings')
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            owner = db.execute("SELECT id FROM users WHERE email='owner@reed.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'owner')",(foreign,owner))
        self.client.post('/workspace/switch',data={'csrf_token':token,'workspace_id':foreign})
        self.assertEqual(self.client.post('/settings',data={**self.payload(),'csrf_token':token}).status_code,400)
        self.assertEqual(self.app.test_client().get('/settings').status_code,303)

    def test_dispatchers_cannot_read_settings_or_write_setup(self):
        self.fixture()
        dispatcher = self.app.test_client()
        self.register(dispatcher,'staff@harbor.test','Staff Separate Business')
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            user = db.execute("SELECT id FROM users WHERE email='staff@harbor.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')",(self.workspace,user))
        dispatcher.post('/workspace/switch',data={'csrf_token':self.csrf(dispatcher,'/inbox'),'workspace_id':self.workspace})
        for path in ('/settings','/setup'):
            self.assertEqual(dispatcher.get(path).status_code,403)
            self.assertEqual(dispatcher.post(path,data={'csrf_token':self.csrf(dispatcher,'/inbox'),'operation':'shared'}).status_code,403)
        self.assertNotIn(b'>Business settings<',dispatcher.get('/inbox').data)

    def test_owner_demoted_after_identity_loading_cannot_write(self):
        enabled = {'value':False}
        @self.app.before_request
        def demote_after_identity():
            if enabled['value'] and request.method=='POST' and request.path in {'/settings','/setup','/workspace/timezone'}:
                with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
                    db.execute("UPDATE memberships SET role='dispatcher' WHERE workspace_id=?",(self.workspace,))
        self.fixture()
        for path in ('/settings','/setup','/workspace/timezone'):
            with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
                db.execute("UPDATE memberships SET role='owner' WHERE workspace_id=?",(self.workspace,))
            payload = {**self.payload(),'operation':'shared'}
            before = self.row()
            enabled['value'] = True
            result = self.client.post(path,data=payload)
            enabled['value'] = False
            self.assertEqual(result.status_code,403)
            self.assertEqual(self.row(),before)

    def test_setup_progress_uses_actual_inquiries_and_explicit_sharing_acknowledgement(self):
        self.fixture()
        self.assertEqual(self.save().status_code,303)
        self.assertIn(b'1 of 3 required steps complete',self.client.get('/setup').data)
        self.client.post('/leads/new',data={'csrf_token':self.csrf(self.client,'/leads/new'),'customer_name':'Internal lead',
            'email':'internal@example.test','service':'AC maintenance','location':'Austin'})
        self.assertIn(b'1 of 3 required steps complete',self.client.get('/setup').data)
        self.app.test_client().get(f'/request/{self.public}')
        self.assertIsNone(self.row()['form_shared_at'])
        self.assertEqual(self.client.post('/setup',data={'csrf_token':self.csrf(self.client,'/setup'),'operation':'shared'}).status_code,303)
        self.assertIn(b'2 of 3 required steps complete',self.client.get('/setup').data)
        self.assertEqual(self.public_post().status_code,303)
        self.assertIn(b'3 of 3 required steps complete',self.client.get('/setup').data)
        self.assertNotIn(b'Set up your business',self.client.get('/inbox').data)
        self.assertEqual(self.client.post('/setup',data={'csrf_token':self.csrf(self.client,'/setup'),'operation':'unshared'}).status_code,303)
        self.assertIsNone(self.row()['form_shared_at'])
        self.assertEqual(self.client.post('/setup',data={'csrf_token':self.csrf(self.client,'/setup'),'operation':'forged'}).status_code,422)

    def test_optional_team_status_does_not_invent_active_members_or_block_solo_business(self):
        self.fixture()
        self.client.post('/team/invite',data={'csrf_token':self.csrf(self.client,'/team'),'email':'sam@example.test'})
        page = self.client.get('/setup')
        self.assertIn(b'Invitation pending',page.data)
        self.assertIn(b'1 active member',page.data)
        self.assertIn(b'Optional',page.data)
        self.assertIn(b'0 of 3 required steps complete',page.data)

    def test_legacy_public_inquiry_counts_but_other_workspace_inquiry_does_not(self):
        self.fixture()
        other = self.app.test_client()
        _,other_public = self.register(other,'other@harbor.test','Harbor Electric')
        self.inquiry(other_public,'Other Customer')
        self.assertIn(b'0 of 3 required steps complete',self.client.get('/setup').data)
        self.inquiry(self.public)
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            db.execute("UPDATE leads SET source='service' WHERE workspace_id=?",(self.workspace,))
        self.assertIn(b'1 of 3 required steps complete',self.client.get('/setup').data)

    def test_html_text_is_escaped_and_marketing_trade_choices_stay_independent(self):
        self.fixture()
        self.assertEqual(self.save(name='<b>Reed</b>',services='<script>alert(1)</script>',service_areas='<b>Austin</b>').status_code,303)
        page = self.app.test_client().get(f'/request/{self.public}')
        self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;',page.data)
        self.assertNotIn(b'<script>alert(1)</script>',page.data)
        marketing = self.app.test_client().get(f'/website/{self.public}/')
        self.assertIn(b'<option value="HVAC"',marketing.data)
        self.assertNotIn(b'<option value="&lt;script',marketing.data)

    def test_contact_phone_requires_digits(self):
        self.fixture()
        before = self.row()
        for phone in ('123----','-------','123456'):
            self.assertEqual(self.save(contact_email='',contact_phone=phone).status_code,422)
            self.assertEqual(self.row(),before)

    def test_mailto_encodes_address_characters_without_changing_recipient(self):
        self.fixture()
        for address in ('service#repairs@example.test','service?repairs@example.test','service%23repairs@example.test'):
            with self.subTest(address=address):
                self.assertEqual(self.save(contact_email=address,contact_phone='').status_code,303)
                page = self.app.test_client().get(f'/request/{self.public}')
                target = re.search(rb'href="(mailto:[^"]+)"',page.data).group(1).decode()
                parsed = urlsplit(target)
                self.assertEqual((parsed.query,parsed.fragment),('',''))
                self.assertEqual(unquote(parsed.path),address)
                self.assertIn('%',target)

    def test_manual_lead_actor_name_cannot_impersonate_customer_form_provenance(self):
        self.fixture()
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            db.execute("UPDATE users SET name='Customer inquiry form'")
        response = self.client.post('/leads/new',data={'csrf_token':self.csrf(self.client,'/leads/new'),
            'customer_name':'Internal lead','email':'internal@example.test','service':'HVAC','location':'Austin','source':'customer_form'})
        self.assertEqual(response.status_code,303)
        self.assertIn(b'0 of 3 required steps complete',self.client.get('/setup').data)
        self.assertEqual(self.public_post('HVAC',source='manual').status_code,303)
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            self.assertEqual(db.execute("SELECT source FROM leads WHERE customer_name='Casey Blake'").fetchone()[0],'customer_form')
        self.assertIn(b'1 of 3 required steps complete',self.client.get('/setup').data)

    def test_settings_timezone_change_preserves_appointment_and_rejects_old_zone_form(self):
        self.fixture()
        lead = self.inquiry(self.public)
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            owner = db.execute('SELECT id FROM users').fetchone()[0]
        payload = {'csrf_token':self.csrf(self.client,f'/leads/{lead}'),'version':'1','operation':'save',
            'appointment_id':'','assigned_user_id':owner,'start':'2026-10-24T10:00','duration_minutes':'60','workspace_timezone':'UTC'}
        self.assertEqual(self.client.post(f'/leads/{lead}/appointment',data=payload).status_code,303)
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            before = db.execute('SELECT * FROM appointments').fetchone()
            payload['appointment_id'] = db.execute('SELECT id FROM appointments').fetchone()[0]
            payload['version'] = '2'
        self.assertEqual(self.save().status_code,303)
        self.assertEqual(self.client.post(f'/leads/{lead}/appointment',data=payload).status_code,409)
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            self.assertEqual(db.execute('SELECT * FROM appointments').fetchone(),before)

    def test_migration_is_additive_idempotent_and_keeps_existing_values(self):
        self.fixture()
        with database(Path(self.temp.name)/'kjancy.sqlite3') as db:
            before = db.execute('SELECT id,name,public_id,created,timezone FROM workspaces').fetchone()
            for column in ('contact_email','contact_phone','services_json','service_areas_json','settings_version','form_shared_at'):
                db.execute(f'ALTER TABLE workspaces DROP COLUMN {column}')
        for _ in range(2):
            create_app({'TESTING':True,'DATA_DIR':self.temp.name,'SECRET_KEY':'test-signing-key'})
        row = self.row()
        self.assertEqual(tuple(row[key] for key in ('id','name','public_id','created','timezone')),before)
        self.assertIsNone(row['services_json'])
        self.assertEqual(row['settings_version'],1)

    def test_backup_restore_retains_settings_and_sharing_state(self):
        from kjancy.backup import create_backup,restore_backup
        self.fixture()
        self.assertEqual(self.save().status_code,303)
        self.client.post('/setup',data={'csrf_token':self.csrf(self.client,'/setup'),'operation':'shared'})
        archive = create_backup(self.temp.name,Path(self.temp.name)/'private-backups')
        restored = restore_backup(archive,Path(self.temp.name)/'recovered')
        with closing(sqlite3.connect(restored/'kjancy.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT name,services_json,service_areas_json,form_shared_at FROM workspaces').fetchone(),
                tuple(self.row()[key] for key in ('name','services_json','service_areas_json','form_shared_at')))
