"""Real request regressions for Admin vs Customer entry points and forms."""
from pathlib import Path
from email import policy
from email.parser import BytesParser
import re
import unittest

import test_customers as customer_cases
from test_app import database


class PortalSeparation(unittest.TestCase):
    setUp = customer_cases.Customers.setUp
    tearDown = customer_cases.Customers.tearDown
    csrf = customer_cases.Customers.csrf
    register = customer_cases.Customers.register
    signup_customer = customer_cases.Customers.signup_customer
    fixture = customer_cases.Customers.fixture

    def test_login_accepts_only_the_account_kind_for_that_portal(self):
        self.fixture()
        for path,address,password in (
                ('/login','customer@home.test','customer-test-password'),
                ('/customer/login','owner@reed.test','a-long-test-password')):
            visitor = self.app.test_client()
            response = visitor.post(path,data={'csrf_token':self.csrf(visitor,path),'email':address,'password':password,'account_kind':'staff'})
            self.assertEqual(response.status_code,422)
            self.assertIn(b'Use ',response.data)
            with visitor.session_transaction() as state: self.assertNotIn('_sid',state)
        for path,address,password,target in (
                ('/login','owner@reed.test','a-long-test-password','/inbox'),
                ('/customer/login','customer@home.test','customer-test-password','/customer')):
            visitor = self.app.test_client()
            response = visitor.post(path,data={'csrf_token':self.csrf(visitor,path),'email':address,'password':password})
            self.assertEqual(response.status_code,303)
            self.assertTrue(response.location.endswith(target))

    def test_authenticated_wrong_portal_does_not_silently_use_current_role(self):
        self.fixture()
        for client,paths,home in ((self.client,('/customer/login','/customer/signup/'+self.public),'/inbox'),
                                  (self.customer,('/login','/signup'),'/customer')):
            with client.session_transaction() as state: original = state['_sid']
            for path in paths:
                page = client.get(path)
                self.assertEqual(page.status_code,403)
                self.assertIn(b'Sign out and switch',page.data)
                self.assertNotIn(b'name="password"',page.data)
                with client.session_transaction() as state: self.assertEqual(state['_sid'],original)
            self.assertEqual(client.get(home).status_code,200)

    def test_explicit_switch_logs_out_current_session_only_and_uses_fixed_destinations(self):
        self.fixture()
        self.assertEqual(self.client.post('/logout',data={'portal':'customer'}).status_code,400)
        response = self.client.post('/logout',data={'csrf_token':self.csrf(self.client,'/inbox'),'portal':'customer','business':self.public})
        self.assertEqual(response.status_code,303)
        self.assertTrue(response.location.startswith('/customer/login?business='))
        self.assertEqual(self.customer.get('/customer').status_code,200)
        self.assertEqual(self.client.get('/inbox').status_code,303)
        response = self.customer.post('/logout',data={'csrf_token':self.csrf(self.customer,'/customer'),'portal':'https://evil.test'})
        self.assertEqual(response.location,'/customer/login')

    def test_signed_out_customer_routes_use_customer_sign_in(self):
        visitor = self.app.test_client()
        for path in ('/customer','/customer/form','/customer/get-started','/customer/requests/unknown'):
            self.assertEqual(visitor.get(path).location,'/customer/login')
        self.assertEqual(visitor.get('/inbox').location,'/login')

    def test_staff_can_preview_guest_fields_but_cannot_submit_a_customer_request(self):
        self.fixture()
        path = '/request/'+self.public
        page = self.client.get(path)
        self.assertEqual(page.status_code,200)
        self.assertIn(b'Admin preview',page.data)
        self.assertIn(b'<fieldset disabled',page.data)
        self.assertNotIn(b'Send inquiry',page.data)
        self.assertNotIn(b'Create a customer account',page.data)
        response = self.client.post(path,data={'csrf_token':self.csrf(self.client,'/inbox'),
            'customer_name':'Forged guest','email':'guest@home.test','service':'HVAC','location':'Oak Street'})
        self.assertEqual(response.status_code,403)
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0],0)
        guest = self.app.test_client()
        self.assertIn(b'Send inquiry',guest.get(path).data)

    def test_customer_public_links_stay_in_owned_business_and_never_save_guest_records(self):
        self.fixture()
        own = '/request/'+self.public
        self.assertEqual(self.customer.get(own).location,'/customer/form')
        other_staff = self.app.test_client()
        _,other_public = self.register(other_staff,email='other@business.test',company='Harbor Electric')
        self.assertEqual(self.customer.get('/request/'+other_public).status_code,403)
        payload = {'csrf_token':self.csrf(self.customer,'/customer'),'customer_name':'Forged guest',
                   'email':'guest@home.test','service':'HVAC','location':'Oak Street'}
        for path in (own,'/request/'+other_public):
            self.assertEqual(self.customer.post(path,data=payload).status_code,403)
        with database(self.path) as db: self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0],0)

    def test_customer_recovery_preserves_selected_portal_without_account_disclosure(self):
        self.fixture()
        visitor = self.app.test_client()
        path = '/account/forgot-password?portal=customer'
        self.assertIn(b'href="/customer/login"',visitor.get(path).data)
        pages = []
        for address in ('customer@home.test','missing@home.test'):
            response = visitor.post(path,data={'csrf_token':self.csrf(visitor,path),'email':address})
            self.assertEqual(response.location,'/account/recovery-requested?portal=customer')
            pages.append(visitor.get(response.location).data)
        self.assertEqual(pages[0],pages[1])
        self.assertIn(b'href="/customer/login"',pages[0])
        self.assertIn(b'portal=customer',pages[0])

    def test_customer_verification_and_reset_return_to_customer_login(self):
        self.fixture()
        def message_path(kind):
            matches = []
            for file in (Path(self.temp.name)/'mail-outbox').glob('*.eml'):
                message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
                if message['To']=='customer@home.test':
                    matches += re.findall(r'/account/'+kind+r'/[A-Za-z0-9_-]{43}',message.get_content())
            self.assertTrue(matches)
            return matches[-1]
        visitor = self.app.test_client()
        verify = message_path('verify')
        self.assertIn(b'href="/customer/login"',visitor.get(verify).data)
        response = visitor.post(verify,data={'csrf_token':self.csrf(visitor,verify)})
        self.assertEqual(response.location,'/customer/login')
        from kjancy.account import issue_link
        from kjancy.db import get_db
        with self.app.test_request_context():
            issue_link(get_db().execute('SELECT * FROM users WHERE id=?',(self.uid,)).fetchone(),'reset')
        reset = message_path('reset')
        response = visitor.post(reset,data={'csrf_token':self.csrf(visitor,reset),'password':'new-customer-password','password_confirm':'new-customer-password'})
        self.assertEqual(response.location,'/customer/login')

    def test_navigation_names_customer_and_admin_scopes_without_cross_role_controls(self):
        self.fixture()
        customer = self.customer.get('/customer').data
        admin = self.client.get('/inbox').data
        self.assertIn(b'Customer portal',customer)
        self.assertNotIn(b'Local workspace',customer)
        self.assertIn(b'Admin workspace',admin)
        for label in (b'href="/inbox"',b'href="/team"',b'href="/settings"',b'href="/reports"'):
            self.assertNotIn(label,customer)
        for label in (b'href="/customer"',b'href="/customer/get-started"',b'href="/customer/form"'):
            self.assertNotIn(label,admin)
