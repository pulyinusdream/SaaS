from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import json
import re
import sqlite3
import time
import unittest

from kjancy import create_app
import test_app as existing
from test_app import database


class Customers(unittest.TestCase):
    setUp = existing.AccountsAndLeads.setUp
    tearDown = existing.AccountsAndLeads.tearDown
    csrf = existing.AccountsAndLeads.csrf
    register = existing.AccountsAndLeads.register
    inquiry = existing.AccountsAndLeads.inquiry

    def fixture(self):
        self.workspace,self.public = self.register()
        self.path = Path(self.temp.name)/'kjancy.sqlite3'
        self.assertEqual(self.app.test_client().get('/customer/signup/'+self.public).status_code,200)
        self.customer = self.signup_customer()
        with database(self.path) as db:
            self.uid = db.execute("SELECT id FROM users WHERE email='customer@home.test'").fetchone()[0]

    def signup_customer(self,address='customer@home.test',public=None):
        client = self.app.test_client()
        path = '/customer/signup/'+(public or self.public)
        result = client.post(path,data={'csrf_token':self.csrf(client,path),'name':'Taylor Morgan','email':address,
            'password':'customer-test-password','role':'owner','account_kind':'staff','workspace_id':'forged'})
        self.assertEqual(result.status_code,303)
        return client

    def form_data(self,client=None,**changes):
        client = client or self.customer
        page = client.get('/customer/form')
        self.assertEqual(page.status_code,200)
        data = {'csrf_token':re.search(rb'name="csrf_token" value="([^"]+)"',page.data)[1].decode(),
                'request_token':re.search(rb'name="request_token" value="([^"]+)"',page.data)[1].decode(),
                'service':'HVAC','location':'19 Oak Street','phone':'555-010-1234','message':'Air conditioning needs attention.'}
        data.update(changes)
        return data

    def submit(self,client=None,**changes):
        client = client or self.customer
        return client.post('/customer/form',data=self.form_data(client,**changes))

    def test_registration_creates_only_customer_and_uses_customer_login(self):
        self.fixture()
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT account_kind FROM users WHERE id=?',(self.uid,)).fetchone()[0],'customer')
            self.assertEqual(db.execute('SELECT count(*) FROM memberships WHERE user_id=?',(self.uid,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT workspace_id FROM customer_accounts WHERE user_id=?',(self.uid,)).fetchone()[0],self.workspace)
            self.assertEqual(db.execute('SELECT count(*) FROM workspaces').fetchone()[0],1)
        self.assertTrue(self.customer.get('/').location.endswith('/customer'))
        for path in ('/customer/login',):
            client = self.app.test_client()
            result = client.post(path,data={'csrf_token':self.csrf(client,path),'email':'customer@home.test','password':'customer-test-password'})
            self.assertTrue(result.location.endswith('/customer'))
        self.assertEqual(self.customer.get('/account/settings').status_code,200)

    def test_customer_cannot_use_any_admin_route_even_with_erroneous_membership(self):
        self.fixture()
        with database(self.path) as db: db.execute("INSERT INTO memberships VALUES(?,?,'owner')",(self.workspace,self.uid))
        for path in ('/inbox','/calendar','/team','/settings','/setup','/reports','/leads/new','/workspaces'):
            with self.subTest(path=path): self.assertEqual(self.customer.get(path).status_code,403)
        result = self.customer.post('/workspace/switch',data={'csrf_token':self.csrf(self.customer,'/customer'),'workspace_id':self.workspace})
        self.assertEqual(result.status_code,403)
        self.assertEqual(self.client.get('/customer').status_code,403)

    def test_contact_setup_validates_retains_defaults_and_blocks_stale_update(self):
        self.fixture()
        def payload(**extra):
            page = self.customer.get('/customer/get-started')
            return {'csrf_token':self.csrf(self.customer,'/customer/get-started'),'version':re.search(rb'name="version" value="(\d+)"',page.data)[1].decode(),
                    'phone':'555-010-1234','location':'19 Oak Street',**extra}
        old = payload()
        for changes in ({'location':''},{'location':'x'*201},{'phone':'bad-number'},{'version':'bad'}):
            self.assertEqual(self.customer.post('/customer/get-started',data=payload(**changes)).status_code,422)
        self.assertEqual(self.customer.post('/customer/get-started',data=old).status_code,303)
        self.assertEqual(self.customer.post('/customer/get-started',data={**old,'location':'Old address'}).status_code,409)
        page = self.customer.get('/customer/form')
        self.assertIn(b'19 Oak Street',page.data)
        self.assertIn(b'555-010-1234',page.data)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT version,location FROM customer_accounts WHERE user_id=?',(self.uid,)).fetchone(),(2,'19 Oak Street'))

    def test_request_ownership_identity_and_business_are_server_controlled(self):
        self.fixture()
        response = self.submit(customer_user_id='forged',user_id='forged',workspace_id='forged',email='attacker@other.test',customer_name='Spoof',status='Closed',source='manual',internal_notes='Injected')
        self.assertEqual(response.status_code,303)
        with database(self.path) as db:
            row = db.execute('SELECT customer_user_id,workspace_id,email,customer_name,status,source,internal_notes FROM leads').fetchone()
            self.assertEqual(row,(self.uid,self.workspace,'customer@home.test','Taylor Morgan','New','customer_portal',''))
        self.assertIn(b'Taylor Morgan',self.client.get('/inbox').data)
        self.assertIn(b'Air conditioning needs attention.',self.customer.get(response.location).data)

    def test_only_owned_requests_visible_and_matching_guest_email_is_not_claimed(self):
        self.fixture()
        own = self.submit()
        second = self.signup_customer('second@home.test')
        other = self.submit(second)
        guest = self.inquiry(self.public,'Guest matching account email')
        with database(self.path) as db: db.execute("UPDATE leads SET email='customer@home.test' WHERE id=?",(guest,))
        page = self.customer.get('/customer')
        self.assertIn(own.location.encode(),page.data)
        self.assertNotIn(other.location.encode(),page.data)
        self.assertNotIn(b'Guest matching account email',page.data)
        self.assertEqual(self.customer.get(other.location).status_code,404)
        self.assertEqual(self.customer.get('/customer/requests/'+guest).status_code,404)
        self.assertEqual(self.customer.get('/leads/'+own.location.rsplit('/',1)[-1]).status_code,403)

    def test_cross_business_customer_ids_cannot_read_or_route_requests(self):
        self.fixture()
        staff = self.app.test_client()
        other_workspace,other_public = self.register(staff,'staff@other.test','Other Business')
        customer = self.signup_customer('other@home.test',other_public)
        response = self.submit(customer,workspace_id=self.workspace)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT workspace_id FROM leads').fetchone()[0],other_workspace)
        self.assertEqual(self.customer.get(response.location).status_code,404)
        self.assertNotIn(response.location.encode(),self.customer.get('/customer?workspace_id='+other_workspace).data)

    def test_customer_detail_projection_hides_notes_outcomes_staff_and_cancel_reason(self):
        self.fixture()
        response = self.submit()
        lead = response.location.rsplit('/',1)[-1]
        now = int(time.time())
        with database(self.path) as db:
            db.execute("UPDATE leads SET status='Contacted',internal_notes='PRIVATE_INTERNAL',followup_action='PRIVATE_FOLLOWUP',followup_outcome='PRIVATE_OUTCOME' WHERE id=?",(lead,))
            db.execute("INSERT INTO appointments(id,workspace_id,lead_id,start_at,end_at,state,cancellation_reason,created,updated) VALUES('appt',?,?,?,?,'cancelled','PRIVATE_CANCEL',?,?)",(self.workspace,lead,now,now+3600,now,now))
        page = self.customer.get(response.location)
        self.assertIn(b'Contacted',page.data)
        self.assertIn(b'Cancelled',page.data)
        for private in (b'PRIVATE_INTERNAL',b'PRIVATE_FOLLOWUP',b'PRIVATE_OUTCOME',b'PRIVATE_CANCEL',b'owner@reed.test'):
            self.assertNotIn(private,page.data)
        self.assertNotIn(b'PRIVATE_',self.customer.get('/customer').data)

    def test_admin_updates_are_reflected_without_customer_mutation_permissions(self):
        self.fixture()
        response = self.submit()
        lead = response.location.rsplit('/',1)[-1]
        result = self.client.post('/leads/'+lead,data={'csrf_token':self.csrf(self.client,'/leads/'+lead),'version':'1','status':'Contacted','internal_notes':'Private notes'})
        self.assertEqual(result.status_code,303)
        self.assertIn(b'Contacted',self.customer.get(response.location).data)
        self.assertEqual(self.customer.post(response.location,data={'csrf_token':self.csrf(self.customer,response.location),'status':'Closed'}).status_code,405)

    def test_form_replay_and_concurrent_posts_create_one_lead(self):
        self.fixture()
        data = self.form_data()
        cookie = self.customer.get_cookie('kjancy_session').value
        clients = [self.app.test_client(),self.app.test_client()]
        for client in clients: client.set_cookie('kjancy_session',cookie)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda c:c.post('/customer/form',data=data),clients))
        self.assertEqual([r.status_code for r in results],[303,303])
        self.assertEqual(results[0].location,results[1].location)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM lead_events').fetchone()[0],1)

    def test_form_token_rejects_other_customer_tamper_expiry_and_changed_catalogue(self):
        self.fixture()
        from itsdangerous.timed import TimestampSigner
        second = self.signup_customer('second@home.test')
        original = self.form_data()
        swapped = self.form_data(second,request_token=original['request_token'])
        self.assertEqual(second.post('/customer/form',data=swapped).status_code,400)
        self.assertEqual(self.customer.post('/customer/form',data={**original,'request_token':'bad'}).status_code,400)
        from unittest.mock import patch
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=int(time.time())+3601):
            # Separate client prevents the artificial clock from poisoning the source cookie.
            expired = self.app.test_client()
            expired.set_cookie('kjancy_session',self.customer.get_cookie('kjancy_session').value)
            self.assertEqual(expired.post('/customer/form',data=original).status_code,400)
        with database(self.path) as db: db.execute('UPDATE workspaces SET services_json=? WHERE id=?',(json.dumps(['Plumbing']),self.workspace))
        self.assertEqual(self.customer.post('/customer/form',data=original).status_code,422)
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0],0)

    def test_customer_cannot_accept_staff_invitation(self):
        self.fixture()
        self.client.post('/team/invite',data={'csrf_token':self.csrf(self.client,'/team'),'email':'customer@home.test'})
        with self.client.session_transaction() as session: token = session['new_invite']['token']
        self.assertEqual(self.customer.get('/invite/'+token).status_code,403)
        self.assertEqual(self.customer.post('/invite/'+token,data={'csrf_token':self.csrf(self.customer,'/customer')}).status_code,403)
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM memberships WHERE user_id=?',(self.uid,)).fetchone()[0],0)

    def test_revocation_or_changed_kind_after_identity_prevents_customer_writes(self):
        self.fixture()
        enabled = {'value':False,'kind':False}
        def mutate():
            if enabled['value']:
                with database(self.path) as db:
                    if enabled['kind']: db.execute("UPDATE users SET account_kind='staff' WHERE id=?",(self.uid,))
                    else: db.execute('DELETE FROM sessions WHERE user_id=?',(self.uid,))
        self.app.before_request_funcs.setdefault(None,[]).append(mutate)
        for kind in (False,True):
            client = self.app.test_client()
            with database(self.path) as db: db.execute("UPDATE users SET account_kind='customer' WHERE id=?",(self.uid,))
            client.post('/customer/login',data={'csrf_token':self.csrf(client,'/customer/login'),'email':'customer@home.test','password':'customer-test-password'})
            payload = self.form_data(client)
            enabled.update(value=True,kind=kind)
            self.assertEqual(client.post('/customer/form',data=payload).status_code,403)
            enabled['value'] = False
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0],0)

    def test_customer_pagination_filter_and_empty_states_are_owned(self):
        self.fixture()
        now = int(time.time())
        with database(self.path) as db:
            db.executemany("INSERT INTO leads(id,workspace_id,customer_user_id,customer_name,service,location,status,created,updated,source) VALUES(?,?,?,'Owned customer','HVAC','Austin','New',?,?,'customer_portal')",[(f'owned-{i}',self.workspace,self.uid,now+i,now+i) for i in range(28)])
        self.assertEqual(self.customer.get('/customer').data.count(b'data-customer-request'),25)
        self.assertEqual(self.customer.get('/customer?page=2').data.count(b'data-customer-request'),3)
        self.assertIn(b'No matching requests',self.customer.get('/customer?status=Closed').data)
        self.assertEqual(self.customer.get('/customer?status=forged').status_code,400)

    def test_email_verification_csrf_origin_and_signup_collision_boundaries(self):
        self.fixture()
        self.app.config['REQUIRE_EMAIL_VERIFICATION'] = True
        self.assertTrue(self.customer.get('/customer').location.endswith('/account/email'))
        self.assertEqual(self.customer.get('/account/settings').status_code,200)
        with database(self.path) as db: db.execute('UPDATE users SET email_verified_at=1 WHERE id=?',(self.uid,))
        self.assertEqual(self.customer.get('/customer').status_code,200)
        self.assertEqual(self.customer.post('/customer/form',data={}).status_code,400)
        self.assertEqual(self.customer.post('/customer/form',data=self.form_data(),headers={'Origin':'https://evil.test'}).status_code,403)
        visitor = self.app.test_client()
        path = '/customer/signup/'+self.public
        response = visitor.post(path,data={'csrf_token':self.csrf(visitor,path),'name':'Collision','email':'owner@reed.test','password':'customer-test-password'})
        self.assertEqual(response.status_code,422)
        self.assertEqual(visitor.get('/customer/signup/unknown-business').status_code,404)

    def test_admin_navigation_moves_customer_functions_and_guest_forms_remain(self):
        self.fixture()
        page = self.client.get('/inbox')
        navigation = re.search(rb'<nav aria-label="Main navigation">(.*?)</nav>',page.data,re.S)[1]
        self.assertNotIn(b'href="/customer/get-started"',navigation)
        self.assertNotIn(b'href="/customer/form"',navigation)
        customer = self.customer.get('/customer')
        self.assertIn(b'href="/customer/get-started"',customer.data)
        self.assertIn(b'href="/customer/form"',customer.data)
        self.assertNotIn(b'href="/inbox"',customer.data)
        self.assertEqual(self.app.test_client().get('/request/'+self.public).status_code,200)

    def test_sample_provision_is_additive_isolated_and_refuses_overwrite_or_production(self):
        self.fixture()
        from kjancy.sample_customer import provision_sample_customer
        credentials = Path(self.temp.name)/'sample-credentials.json'
        result = provision_sample_customer(self.app,'owner@reed.test',credentials)
        saved = json.loads(credentials.read_text())
        self.assertEqual(saved['email'],'sample.customer@kjancy.test')
        sample = self.app.test_client()
        response = sample.post('/customer/login',data={'csrf_token':self.csrf(sample,'/customer/login'),'email':saved['email'],'password':saved['password']})
        self.assertEqual(response.status_code,303)
        self.assertIn(b'Sample Customer Workspace',sample.get('/customer').data)
        with database(self.path) as db:
            sample_id,business = db.execute("SELECT c.user_id,c.workspace_id FROM customer_accounts c JOIN users u ON u.id=c.user_id WHERE u.email='sample.customer@kjancy.test'").fetchone()
            self.assertNotEqual(business,self.workspace)
            self.assertEqual(db.execute('SELECT count(*) FROM memberships WHERE user_id=?',(sample_id,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT name FROM users WHERE id=?',(self.uid,)).fetchone()[0],'Taylor Morgan')
        with self.assertRaises(ValueError): provision_sample_customer(self.app,'owner@reed.test',Path(self.temp.name)/'other.json')
        self.app.config['MAIL_MODE'] = 'smtp'
        with self.assertRaises(ValueError): provision_sample_customer(self.app,'owner@reed.test',Path(self.temp.name)/'production.json')

    def test_upgrade_keeps_legacy_staff_and_guest_records_unowned(self):
        self.fixture()
        guest = self.inquiry(self.public)
        config = {'TESTING':True,'DATA_DIR':self.temp.name,'SECRET_KEY':'test-signing-key'}
        create_app(config)
        create_app(config)
        with database(self.path) as db:
            self.assertEqual(db.execute("SELECT account_kind FROM users WHERE email='owner@reed.test'").fetchone()[0],'staff')
            self.assertIsNone(db.execute('SELECT customer_user_id FROM leads WHERE id=?',(guest,)).fetchone()[0])
        from kjancy.backup import create_backup,restore_backup
        archive = create_backup(self.temp.name,Path(self.temp.name)/'backups')
        destination = restore_backup(archive,Path(self.temp.name)/'recovered')
        with closing(sqlite3.connect(destination/'kjancy.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT workspace_id FROM customer_accounts WHERE user_id=?',(self.uid,)).fetchone()[0],self.workspace)

    def test_customer_account_settings_return_to_portal_instead_of_denied_admin_page(self):
        self.fixture()
        response = self.customer.get('/account/settings')
        self.assertIn(b'href="/customer"',response.data)
        self.assertNotIn(b'href="/workspaces"',response.data)
