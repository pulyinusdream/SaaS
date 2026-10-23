from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re
import sqlite3
import time
import unittest
from unittest.mock import patch

from kjancy import create_app
import test_customers as fixtures
from test_app import database


class Conversations(unittest.TestCase):
    tearDown = fixtures.Customers.tearDown
    csrf = fixtures.Customers.csrf
    register = fixtures.Customers.register
    signup_customer = fixtures.Customers.signup_customer
    form_data = fixtures.Customers.form_data
    submit = fixtures.Customers.submit

    def setUp(self):
        fixtures.Customers.setUp(self)
        fixtures.Customers.fixture(self)
        self.customer_path = self.submit().location
        self.lead = self.customer_path.rsplit('/',1)[-1]
        self.admin_path = '/leads/'+self.lead

    def token(self,client,path,name):
        page = client.get(path)
        self.assertEqual(page.status_code,200)
        found = re.search(('name="'+name+'" value="([^"]+)"').encode(),page.data)
        self.assertIsNotNone(found,'Expected protected '+name+' control')
        return found[1].decode()

    def reply_data(self,**changes):
        return {'csrf_token':self.csrf(self.client,self.admin_path),
                'reply_token':self.token(self.client,self.admin_path,'reply_token'),
                'reply_message':'We can discuss the next visit tomorrow.',**changes}

    def customer_message(self,body='Any news about my request?'):
        token = self.token(self.customer,self.customer_path,'message_token')
        result = self.customer.post(self.customer_path+'/messages',data={
            'csrf_token':self.csrf(self.customer,self.customer_path),'message_token':token,'followup_message':body})
        self.assertEqual(result.status_code,303)

    def mark(self,client,path,token=None):
        return client.post(path+'/messages/read',data={'csrf_token':self.csrf(client,path),
            'read_token':token or self.token(client,path,'read_token')})

    def test_admin_reply_is_customer_visible_and_preserves_private_request_state(self):
        with database(self.path) as db:
            db.execute("UPDATE leads SET internal_notes='PRIVATE_STAFF_NOTE',status='Closed' WHERE id=?",(self.lead,))
        result = self.client.post(self.admin_path+'/messages',data=self.reply_data(
            reply_message='Tomorrow works.\n<script>bad()</script>',customer_user_id='forged',workspace_id='forged',sender_kind='customer'))
        self.assertEqual(result.status_code,303)
        for client,path in ((self.client,self.admin_path),(self.customer,self.customer_path)):
            page = client.get(path)
            self.assertIn(b'Tomorrow works.',page.data)
            self.assertIn(b'&lt;script&gt;bad()&lt;/script&gt;',page.data)
            self.assertIn(b'Business reply',page.data)
        self.assertNotIn(b'PRIVATE_STAFF_NOTE',self.customer.get(self.customer_path).data)
        with database(self.path) as db:
            row = db.execute('SELECT customer_user_id,sender_kind,staff_user_id FROM customer_request_messages').fetchone()
            self.assertEqual(row[:2],(self.uid,'staff'))
            self.assertEqual(row[2],db.execute("SELECT id FROM users WHERE email='owner@reed.test'").fetchone()[0])
            self.assertEqual(db.execute('SELECT status,version,internal_notes FROM leads WHERE id=?',(self.lead,)).fetchone(),('Closed',1,'PRIVATE_STAFF_NOTE'))

    def test_unread_counts_are_directional_and_get_never_marks_read(self):
        self.customer_message()
        self.assertIn(b'1 unread',self.client.get('/inbox').data)
        self.assertNotIn(b'1 unread',self.customer.get('/customer').data)
        self.client.get(self.admin_path)
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM request_message_reads').fetchone()[0],0)
        self.assertEqual(self.mark(self.client,self.admin_path).status_code,303)
        self.assertNotIn(b'1 unread',self.client.get('/inbox').data)
        self.assertEqual(self.client.post(self.admin_path+'/messages',data=self.reply_data()).status_code,303)
        self.assertIn(b'1 unread',self.customer.get('/customer').data)
        self.assertNotIn(b'1 unread',self.client.get('/inbox').data)
        self.assertEqual(self.mark(self.customer,self.customer_path).status_code,303)
        self.assertNotIn(b'1 unread',self.customer.get('/customer').data)

    def test_mark_read_preserves_new_arrivals_and_other_staff_unread_state(self):
        self.customer_message('First customer message')
        first_token = self.token(self.client,self.admin_path,'read_token')
        self.customer_message('Second customer message')
        self.assertEqual(self.mark(self.client,self.admin_path,first_token).status_code,303)
        self.assertIn(b'1 unread',self.client.get('/inbox').data)
        second_staff = self.app.test_client()
        self.register(second_staff,'second@business.test','Second Business')
        with database(self.path) as db:
            staff = db.execute("SELECT id FROM users WHERE email='second@business.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')",(self.workspace,staff))
        second_staff.post('/workspace/switch',data={'csrf_token':self.csrf(second_staff,'/inbox'),'workspace_id':self.workspace})
        self.assertIn(b'2 unread',second_staff.get('/inbox').data)
        self.assertEqual(self.mark(second_staff,self.admin_path,first_token).status_code,400)
        self.assertIn(b'2 unread',second_staff.get('/inbox').data)

    def test_paginated_read_only_marks_displayed_messages_and_replay_is_safe(self):
        with database(self.path) as db:
            for i in range(26):
                db.execute('INSERT INTO customer_request_messages(lead_id,workspace_id,customer_user_id,sender_name,body,submission_key,created) VALUES(?,?,?,?,?,?,?)',
                    (self.lead,self.workspace,self.uid,'Taylor',f'Customer message {i}',f'page-{i}',int(time.time())+i))
        token = self.token(self.client,self.admin_path,'read_token')
        for _ in range(2): self.assertEqual(self.mark(self.client,self.admin_path,token).status_code,303)
        self.assertIn(b'1 unread',self.client.get('/inbox').data)
        page_two = self.admin_path+'?messages_page=2'
        last_token = self.token(self.client,page_two,'read_token')
        self.assertEqual(self.mark(self.client,self.admin_path,last_token).status_code,303)
        self.assertNotIn(b'1 unread',self.client.get('/inbox').data)
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM request_message_reads').fetchone()[0],26)

    def test_reply_validation_token_scopes_and_guest_request_have_no_writes(self):
        for text in ('','   ','x'*2001,'bad\x00text'):
            page = self.client.post(self.admin_path+'/messages',data=self.reply_data(reply_message=text))
            self.assertEqual(page.status_code,422)
            self.assertIn(b'aria-invalid="true"',page.data)
        data = self.reply_data()
        second_path = self.submit().location.replace('/customer/requests/','/leads/')
        self.assertEqual(self.client.post(second_path+'/messages',data=data).status_code,400)
        self.assertEqual(self.client.post(self.admin_path+'/messages',data={**data,'reply_token':'bad'}).status_code,400)
        self.assertEqual(self.client.post(self.admin_path+'/messages',data={**data,'csrf_token':'bad'}).status_code,400)
        self.assertEqual(self.client.post(self.admin_path+'/messages',data=data,headers={'Origin':'https://other.test'}).status_code,403)
        self.assertEqual(self.customer.post(self.admin_path+'/messages',data={**data,'csrf_token':self.csrf(self.customer,self.customer_path)}).status_code,403)
        other_customer = self.signup_customer('other@home.test')
        self.assertEqual(other_customer.get(self.customer_path).status_code,404)
        with database(self.path) as db:
            db.execute('UPDATE leads SET customer_user_id=NULL WHERE id=?',(self.lead,))
        self.assertNotIn(b'name="reply_token"',self.client.get(self.admin_path).data)
        self.assertEqual(self.client.post(self.admin_path+'/messages',data=data).status_code,404)
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM customer_request_messages').fetchone()[0],0)

    def test_concurrent_reply_replay_saves_one_message_and_event(self):
        data = self.reply_data()
        cookie = self.client.get_cookie('kjancy_session').value
        clients = [self.app.test_client(),self.app.test_client()]
        for client in clients: client.set_cookie('kjancy_session',cookie)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda c:c.post(self.admin_path+'/messages',data=data),clients))
        self.assertEqual([r.status_code for r in results],[303,303])
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM customer_request_messages').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM lead_events WHERE description='Business reply sent to customer'").fetchone()[0],1)

    def test_reply_rechecks_membership_and_read_token_rejects_wrong_request(self):
        self.customer_message()
        data = self.reply_data()
        read_token = self.token(self.client,self.admin_path,'read_token')
        second_path = self.submit().location.replace('/customer/requests/','/leads/')
        self.assertEqual(self.mark(self.client,second_path,read_token).status_code,400)
        def remove_membership():
            from flask import request
            if request.method=='POST' and request.path==self.admin_path+'/messages':
                with database(self.path) as db: db.execute('DELETE FROM memberships WHERE workspace_id=?',(self.workspace,))
        self.app.before_request_funcs.setdefault(None,[]).append(remove_membership)
        self.assertEqual(self.client.post(self.admin_path+'/messages',data=data).status_code,404)
        with database(self.path) as db: self.assertEqual(db.execute("SELECT count(*) FROM customer_request_messages WHERE sender_kind='staff'").fetchone()[0],0)

    def test_migration_preserves_legacy_messages_and_creates_unread_state_without_rewriting(self):
        # Rebuild only the legacy one-way table in the isolated fixture, then run startup twice.
        with database(self.path) as db:
            db.execute('DROP TABLE IF EXISTS request_message_reads')
            db.execute('DROP TABLE customer_request_messages')
            db.execute('CREATE TABLE customer_request_messages(id INTEGER PRIMARY KEY,lead_id TEXT NOT NULL,workspace_id TEXT NOT NULL,customer_user_id TEXT NOT NULL,sender_name TEXT NOT NULL,body TEXT NOT NULL,submission_key TEXT UNIQUE NOT NULL,created INTEGER NOT NULL)')
            db.execute('INSERT INTO customer_request_messages VALUES(5,?,?,?,?,?,?,?)',(self.lead,self.workspace,self.uid,'Legacy customer','Saved before upgrade','legacy-key',100))
        for _ in range(2): create_app({'TESTING':True,'DATA_DIR':self.temp.name,'SECRET_KEY':'test-signing-key'})
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT id,sender_name,body,submission_key,created,sender_kind,staff_user_id FROM customer_request_messages').fetchone(),(5,'Legacy customer','Saved before upgrade','legacy-key',100,'customer',None))
            self.assertEqual(db.execute('SELECT count(*) FROM request_message_reads').fetchone()[0],0)

    def test_expired_reply_and_read_tokens_and_cross_business_replays_are_rejected(self):
        self.customer_message()
        reply = self.reply_data()
        read = {'csrf_token':self.csrf(self.client,self.admin_path),'read_token':self.token(self.client,self.admin_path,'read_token')}
        cookie = self.client.get_cookie('kjancy_session').value
        for suffix,data in (('/messages',reply),('/messages/read',read)):
            expired = self.app.test_client()
            expired.set_cookie('kjancy_session',cookie)
            with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=int(time.time())+3601):
                self.assertEqual(expired.post(self.admin_path+suffix,data=data).status_code,400)
        other_staff = self.app.test_client()
        self.register(other_staff,'foreign@business.test','Foreign Business')
        other_csrf = self.csrf(other_staff,'/inbox')
        for suffix,data in (('/messages',reply),('/messages/read',read)):
            self.assertEqual(other_staff.post(self.admin_path+suffix,data={**data,'csrf_token':other_csrf}).status_code,404)
        other_customer = self.signup_customer('foreign@home.test')
        self.assertEqual(other_customer.post(self.customer_path+'/messages/read',data={**read,'csrf_token':self.csrf(other_customer,'/customer')}).status_code,404)
        self.assertEqual(self.client.post(self.admin_path+'/messages/read',data={**read,'read_token':'tampered'}).status_code,400)
        self.assertEqual(self.client.post(self.admin_path+'/messages/read',data={**read,'csrf_token':'bad'}).status_code,400)
        self.assertEqual(self.client.post(self.admin_path+'/messages/read',data=read,headers={'Origin':'https://foreign.test'}).status_code,403)
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM request_message_reads').fetchone()[0],0)

    def test_both_admin_writes_recheck_session_role_membership_and_recipient_after_identity(self):
        self.customer_message()
        foreign = self.app.test_client()
        foreign_workspace,_ = self.register(foreign,'foreign@business.test','Foreign Business')
        with database(self.path) as db: owner = db.execute("SELECT id FROM users WHERE email='owner@reed.test'").fetchone()[0]
        armed = {'mode':None}
        def change_after_identity():
            from flask import request
            if request.method!='POST' or not request.path.startswith(self.admin_path+'/messages') or not armed['mode']: return
            with database(self.path) as db:
                if armed['mode']=='session': db.execute('DELETE FROM sessions WHERE user_id=?',(owner,))
                elif armed['mode']=='role': db.execute("UPDATE users SET account_kind='customer' WHERE id=?",(owner,))
                elif armed['mode']=='membership': db.execute('DELETE FROM memberships WHERE workspace_id=? AND user_id=?',(self.workspace,owner))
                elif armed['mode']=='recipient': db.execute('UPDATE customer_accounts SET workspace_id=? WHERE user_id=?',(foreign_workspace,self.uid))
        self.app.before_request_funcs.setdefault(None,[]).append(change_after_identity)
        for mode,expected in (('session',403),('role',403),('membership',404),('recipient',404)):
            for suffix in ('/messages','/messages/read'):
                with self.subTest(mode=mode,suffix=suffix):
                    armed['mode']=None
                    with database(self.path) as db:
                        db.execute("UPDATE users SET account_kind='staff' WHERE id=?",(owner,))
                        db.execute("INSERT OR IGNORE INTO memberships VALUES(?,?,'owner')",(self.workspace,owner))
                        db.execute('UPDATE customer_accounts SET workspace_id=? WHERE user_id=?',(self.workspace,self.uid))
                    self.client = self.app.test_client()
                    self.client.post('/login',data={'csrf_token':self.csrf(self.client,'/login'),'email':'owner@reed.test','password':'a-long-test-password'})
                    data = self.reply_data() if suffix=='/messages' else {'csrf_token':self.csrf(self.client,self.admin_path),'read_token':self.token(self.client,self.admin_path,'read_token')}
                    armed['mode']=mode
                    self.assertEqual(self.client.post(self.admin_path+suffix,data=data).status_code,expected)
                    armed['mode']=None
        with database(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM customer_request_messages WHERE sender_kind='staff'").fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM request_message_reads').fetchone()[0],0)
