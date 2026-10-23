import re
import time
from unittest.mock import patch

import test_customers as fixtures
from test_app import database


class CustomerMessages(fixtures.Customers):
    # Reuse the existing real Flask/SQLite fixture, without inheriting its test cases.
    def setUp(self):
        super().setUp()
        self.fixture()
        self.request_url = self.submit().location
        self.lead = self.request_url.rsplit('/', 1)[-1]
        self.message_url = self.request_url + '/messages'

    def message_data(self, client=None, path=None, **changes):
        client, path = client or self.customer, path or self.request_url
        page = client.get(path)
        token = re.search(rb'name="message_token" value="([^"]+)"', page.data)
        self.assertIsNotNone(token, 'The customer request must have a follow-up form')
        data = {'csrf_token': self.csrf(client, path), 'message_token': token[1].decode(),
                'followup_message': 'Could you update me on this request?'}
        data.update(changes)
        return data

    def test_customer_message_reaches_only_matching_admin_and_preserves_request(self):
        text = 'Please call tomorrow.\n<script>alert(1)</script>'
        result = self.customer.post(self.message_url, data=self.message_data(followup_message=text,
            workspace_id='forged', customer_user_id='forged', status='Closed'))
        self.assertEqual(result.status_code, 303)
        self.assertIn('#follow-up-messages', result.location)
        customer_page = self.customer.get(result.location)
        admin_page = self.client.get('/leads/' + self.lead)
        for page in (customer_page, admin_page):
            self.assertIn(b'Please call tomorrow.', page.data)
            self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;', page.data)
            self.assertNotIn(b'<script>alert(1)</script>', page.data)
        self.assertIn(b'1 customer message', self.client.get('/inbox').data)
        self.assertIn(b'#follow-up-messages', self.customer.get('/customer').data)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT workspace_id,customer_user_id,body FROM customer_request_messages').fetchone(), (self.workspace,self.uid,text))
            self.assertEqual(db.execute('SELECT status,version,internal_notes FROM leads WHERE id=?',(self.lead,)).fetchone(),('New',1,''))
            self.assertEqual(db.execute("SELECT count(*) FROM lead_events WHERE description='Customer follow-up message received'").fetchone()[0],1)

    def test_invalid_messages_retain_input_and_do_not_save(self):
        for body in ('', '   ', 'x'*2001, 'bad\x00text'):
            with self.subTest(body=body[:10]):
                page = self.customer.post(self.message_url,data=self.message_data(followup_message=body))
                self.assertEqual(page.status_code,422)
                self.assertIn(b'aria-invalid="true"',page.data)
                self.assertIn(b'Send follow-up',page.data)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM customer_request_messages').fetchone()[0],0)

    def test_replay_creates_one_message_and_one_event(self):
        data = self.message_data()
        for _ in range(2): self.assertEqual(self.customer.post(self.message_url,data=data).status_code,303)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM customer_request_messages').fetchone()[0],1)
            self.assertEqual(db.execute("SELECT count(*) FROM lead_events WHERE description='Customer follow-up message received'").fetchone()[0],1)

    def test_scope_checks_other_customer_business_staff_guest_and_swapped_request(self):
        data = self.message_data()
        other = self.signup_customer('other@home.test')
        other_request = self.submit(other).location
        self.assertEqual(other.post(self.message_url,data={**data,'csrf_token':self.csrf(other,'/customer')}).status_code,404)
        self.assertEqual(self.customer.post(other_request+'/messages',data=data).status_code,404)
        own_second = self.submit().location
        self.assertEqual(self.customer.post(own_second+'/messages',data=data).status_code,400)
        self.assertEqual(self.client.post(self.message_url,data={**data,'csrf_token':self.csrf(self.client,'/inbox')}).status_code,403)
        outsider = self.app.test_client()
        self.register(outsider,'outsider@business.test','Other Business')
        self.assertEqual(outsider.get('/leads/'+self.lead).status_code,404)
        anonymous = self.app.test_client()
        self.assertEqual(anonymous.post(self.message_url,data={**data,'csrf_token':self.csrf(anonymous,'/customer/login')}).status_code,303)
        self.assertEqual(self.customer.post(self.message_url,data={**data,'message_token':'bad'}).status_code,400)
        with patch('itsdangerous.timed.TimestampSigner.get_timestamp',return_value=int(time.time())+3601):
            self.assertEqual(self.customer.post(self.message_url,data=data).status_code,400)

    def test_csrf_origin_and_revoked_session_cannot_write(self):
        data = self.message_data()
        self.assertEqual(self.customer.post(self.message_url,data={**data,'csrf_token':'bad'}).status_code,400)
        self.assertEqual(self.customer.post(self.message_url,data=data,headers={'Origin':'https://other.test'}).status_code,403)
        with database(self.path) as db: db.execute('DELETE FROM sessions WHERE user_id=?',(self.uid,))
        self.assertEqual(self.customer.post(self.message_url,data=data).status_code,400)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM customer_request_messages').fetchone()[0],0)

    def test_closed_requests_accept_followup_and_history_is_paginated_private(self):
        with database(self.path) as db:
            db.execute("UPDATE leads SET status='Closed',internal_notes='PRIVATE_ADMIN_NOTE' WHERE id=?",(self.lead,))
        self.assertEqual(self.customer.post(self.message_url,data=self.message_data()).status_code,303)
        with database(self.path) as db:
            for i in range(26):
                db.execute('INSERT INTO customer_request_messages(lead_id,workspace_id,customer_user_id,sender_name,body,submission_key,created) VALUES(?,?,?,?,?,?,?)',
                    (self.lead,self.workspace,self.uid,'Taylor Morgan',f'History message {i:02}',f'fixture-{i}',2000000000+i))
        for path, client in ((self.request_url,self.customer),('/leads/'+self.lead,self.client)):
            first = client.get(path)
            self.assertIn(b'History message 25',first.data)
            self.assertNotIn(b'History message 00',first.data)
            self.assertIn(b'Older messages',first.data)
            older = client.get(path+'?messages_page=2')
            self.assertIn(b'History message 00',older.data)
        self.assertNotIn(b'PRIVATE_ADMIN_NOTE',self.customer.get(self.request_url).data)


# Only collect this feature's six cases; the base class suite runs separately.
for name in list(dir(CustomerMessages)):
    if name.startswith('test_') and name not in CustomerMessages.__dict__:
        setattr(CustomerMessages,name,None)
