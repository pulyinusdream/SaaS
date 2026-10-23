import re
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from kjancy import create_app


@contextmanager
def database(path):
    connection = sqlite3.connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


class AccountsAndLeads(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[3] / 'work' / 'saas' / 'test-data'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.app = create_app({'TESTING': True, 'DATA_DIR': self.temp.name, 'SECRET_KEY': 'test-signing-key'})
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp.cleanup()

    def test_business_can_open_registration(self):
        response = self.client.get('/signup')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'Create your workspace', response.data)

    def csrf(self, client, path='/login'):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match.group(1).decode()

    def register(self, client=None, email='owner@reed.test', company='Reed Home Services'):
        client = client or self.client
        response = client.post('/signup', data={
            'csrf_token': self.csrf(client, '/signup'), 'name': 'Jordan Reed',
            'company': company, 'email': email, 'password': 'a-long-test-password',
        })
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.location.endswith('/inbox'))
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            return db.execute('SELECT id,public_id FROM workspaces WHERE name=?', (company,)).fetchone()

    def inquiry(self, public_id, name='Taylor Morgan'):
        public = self.app.test_client()
        response = public.post(f'/request/{public_id}', data={
            'csrf_token': self.csrf(public, f'/request/{public_id}'),
            'customer_name': name, 'email': 'taylor@example.test', 'phone': '555-010-2040',
            'service': 'HVAC', 'location': 'North Austin', 'message': 'AC is not cooling.',
        })
        self.assertEqual(response.status_code, 303)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            return db.execute('SELECT id FROM leads WHERE customer_name=? ORDER BY created DESC', (name,)).fetchone()[0]

    def test_signup_persists_a_hashed_password_and_company(self):
        self.register()
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            hashed = db.execute('SELECT password_hash FROM users').fetchone()[0]
        self.assertNotIn('a-long-test-password', hashed)
        self.assertTrue(hashed.startswith('scrypt:'))
        self.assertIn(b'Reed Home Services', self.client.get('/inbox').data)

    def test_signup_rejects_short_password_and_duplicate_email(self):
        self.register()
        other = self.app.test_client()
        token = self.csrf(other, '/signup')
        for password in ['short', 'a-long-test-password']:
            response = other.post('/signup', data={'csrf_token': token, 'name': 'Other Owner', 'company': 'Other Services', 'email': 'OWNER@REED.TEST', 'password': password})
            self.assertEqual(response.status_code, 422)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM workspaces').fetchone()[0], 1)

    def test_login_logout_and_session_revocation(self):
        self.register()
        old_cookie = self.client.get_cookie('kjancy_session').value
        token = self.csrf(self.client, '/inbox')
        self.assertEqual(self.client.post('/logout', data={'csrf_token': token}).status_code, 303)
        replay = self.app.test_client()
        replay.set_cookie('kjancy_session', old_cookie)
        self.assertEqual(replay.get('/inbox').status_code, 303)
        token = self.csrf(self.client)
        self.assertEqual(self.client.post('/login', data={'csrf_token': token, 'email': 'owner@reed.test', 'password': 'incorrect'}).status_code, 422)
        response = self.client.post('/login', data={'csrf_token': token, 'email': 'owner@reed.test', 'password': 'a-long-test-password'})
        self.assertEqual(response.status_code, 303)
        self.assertNotEqual(self.client.get_cookie('kjancy_session').value, old_cookie)

    def test_accounts_and_leads_survive_app_restart(self):
        _, public_id = self.register()
        self.inquiry(public_id)
        restarted = create_app({'TESTING': True, 'DATA_DIR': self.temp.name, 'SECRET_KEY': 'test-signing-key'})
        client = restarted.test_client()
        token = self.csrf(client)
        client.post('/login', data={'csrf_token': token, 'email': 'owner@reed.test', 'password': 'a-long-test-password'})
        self.assertIn(b'Taylor Morgan', client.get('/inbox').data)

    def test_two_businesses_cannot_read_or_update_each_others_leads(self):
        first_id, public_id = self.register()
        lead_id = self.inquiry(public_id)
        second = self.app.test_client()
        second_id, second_public = self.register(second, 'owner@harbor.test', 'Harbor Electric')
        second_lead = self.inquiry(second_public, 'Casey Blake')
        self.assertNotIn(b'Taylor Morgan', second.get('/inbox').data)
        self.assertNotIn(b'Casey Blake', self.client.get('/inbox').data)
        self.assertEqual(second.get(f'/leads/{lead_id}').status_code, 404)
        response = second.post(f'/leads/{lead_id}', data={'csrf_token': self.csrf(second, '/inbox'), 'status': 'Closed', 'version': '1'})
        self.assertEqual(response.status_code, 404)
        response = second.post('/workspace/switch', data={'csrf_token': self.csrf(second, '/inbox'), 'workspace_id': first_id})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.client.get(f'/leads/{second_lead}').status_code, 404)

    def test_public_form_derives_company_from_url_not_submitted_id(self):
        first_id, public_id = self.register()
        second = self.app.test_client()
        second_id, _ = self.register(second, 'owner@harbor.test', 'Harbor Electric')
        public = self.app.test_client()
        response = public.post(f'/request/{public_id}', data={'csrf_token': self.csrf(public, f'/request/{public_id}'), 'customer_name': 'Drew Collins', 'email': 'drew@example.test', 'service': 'Plumbing', 'location': 'West Austin', 'workspace_id': second_id, 'status': 'Closed'})
        self.assertEqual(response.status_code, 303)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            row = db.execute("SELECT workspace_id,status FROM leads WHERE customer_name='Drew Collins'").fetchone()
        self.assertEqual(row, (first_id, 'New'))

    def test_public_form_requires_valid_contact_and_does_not_expose_leads(self):
        _, public_id = self.register()
        public = self.app.test_client()
        response = public.post(f'/request/{public_id}', data={'csrf_token': self.csrf(public, f'/request/{public_id}'), 'customer_name': 'Taylor Morgan', 'email': 'invalid', 'service': 'HVAC', 'location': 'Austin'})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(b'owner@reed.test', public.get(f'/request/{public_id}').data)
        self.assertEqual(public.get('/inbox').status_code, 303)
        self.assertEqual(public.get('/request/not-a-real-company').status_code, 404)

    def test_status_update_persists_and_rejects_stale_or_invalid_updates(self):
        _, public_id = self.register()
        lead_id = self.inquiry(public_id)
        path = f'/leads/{lead_id}'
        token = self.csrf(self.client, path)
        self.assertEqual(self.client.post(path, data={'csrf_token': token, 'status': 'Contacted', 'version': '1', 'internal_notes': 'Called customer.'}).status_code, 303)
        self.assertIn(b'Called customer.', self.client.get(path).data)
        self.assertEqual(self.client.post(path, data={'csrf_token': token, 'status': 'Closed', 'version': '1'}).status_code, 409)
        self.assertEqual(self.client.post(path, data={'csrf_token': token, 'status': 'invented', 'version': '2'}).status_code, 422)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            self.assertEqual(db.execute('SELECT status,version FROM leads WHERE id=?', (lead_id,)).fetchone(), ('Contacted', 2))
            self.assertEqual(db.execute('SELECT count(*) FROM lead_events WHERE lead_id=?', (lead_id,)).fetchone()[0], 2)

    def test_search_and_filters_remain_tenant_scoped(self):
        _, public_id = self.register()
        lead_id = self.inquiry(public_id)
        self.assertIn(b'Taylor Morgan', self.client.get('/inbox?q=Taylor').data)
        self.assertNotIn(b'Taylor Morgan', self.client.get('/inbox?status=Closed').data)
        self.assertNotIn(b'Taylor Morgan', self.client.get('/inbox?q=%27+OR+1%3D1--').data)
        self.assertEqual(self.client.get('/inbox?status=not-valid').status_code, 400)

    def test_html_input_is_escaped_in_owner_inbox(self):
        _, public_id = self.register()
        self.inquiry(public_id, '<script>alert(1)</script>')
        page = self.client.get('/inbox').data
        self.assertNotIn(b'<script>alert(1)</script>', page)
        self.assertIn(b'&lt;script&gt;', page)

    def test_write_requires_csrf_and_same_origin(self):
        self.assertEqual(self.client.post('/signup', data={'name': 'Test'}).status_code, 400)
        token = self.csrf(self.client, '/signup')
        response = self.client.post('/signup', data={'csrf_token': token}, headers={'Origin': 'https://untrusted.test'})
        self.assertEqual(response.status_code, 403)
        response = self.client.post('/signup', data={'csrf_token': 'non-ascii-\u00e9'})
        self.assertEqual(response.status_code, 400)

    def test_untrusted_host_is_rejected_and_headers_protect_private_pages(self):
        self.assertEqual(self.client.get('/signup', headers={'Host': 'untrusted.test'}).status_code, 400)
        self.register()
        response = self.client.get('/inbox')
        self.assertIn("default-src 'self'", response.headers['Content-Security-Policy'])
        self.assertIn('no-store', response.headers['Cache-Control'])
        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')

    def test_dispatcher_invitation_is_owner_only_scoped_and_single_use(self):
        first_id, public_id = self.register()
        lead_id = self.inquiry(public_id)
        dispatcher = self.app.test_client()
        self.register(dispatcher, 'dispatcher@harbor.test', 'Harbor Electric')
        token = self.csrf(self.client, '/team')
        response = self.client.post('/team/invite', data={'csrf_token': token, 'email': 'dispatcher@harbor.test'})
        self.assertEqual(response.status_code, 303)
        page = self.client.get('/team').data
        invite = re.search(rb'/invite/([a-zA-Z0-9_-]+)', page).group(1).decode()
        token = self.csrf(dispatcher, f'/invite/{invite}')
        self.assertEqual(dispatcher.post(f'/invite/{invite}', data={'csrf_token': token}).status_code, 303)
        self.assertIn(b'Taylor Morgan', dispatcher.get('/inbox').data)
        self.assertEqual(dispatcher.post('/team/invite', data={'csrf_token': self.csrf(dispatcher, '/inbox'), 'email': 'other@example.test'}).status_code, 403)
        self.assertEqual(dispatcher.post(f'/invite/{invite}', data={'csrf_token': self.csrf(dispatcher, '/inbox')}).status_code, 410)
        token = self.csrf(dispatcher, f'/leads/{lead_id}')
        self.assertEqual(dispatcher.post(f'/leads/{lead_id}', data={'csrf_token': token, 'status': 'Contacted', 'version': '1'}).status_code, 303)

    def test_invitation_cannot_be_claimed_by_another_email_and_expires(self):
        self.register()
        response = self.client.post('/team/invite', data={'csrf_token': self.csrf(self.client, '/team'), 'email': 'invited@example.test'})
        self.assertEqual(response.status_code, 303)
        invite = re.search(rb'/invite/([a-zA-Z0-9_-]+)', self.client.get('/team').data).group(1).decode()
        other = self.app.test_client()
        self.register(other, 'other@example.test', 'Other Business')
        token = self.csrf(other, '/inbox')
        self.assertEqual(other.post(f'/invite/{invite}', data={'csrf_token': token}).status_code, 403)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            db.execute('UPDATE invitations SET expires=0')
        self.assertEqual(other.get(f'/invite/{invite}').status_code, 410)

    def test_login_is_rate_limited(self):
        token = self.csrf(self.client)
        responses = [self.client.post('/login', data={'csrf_token': token, 'email': 'unknown@example.test', 'password': 'wrong'}) for _ in range(13)]
        self.assertEqual(responses[-1].status_code, 429)

    def test_stale_form_cannot_create_a_lead_in_a_newly_selected_workspace(self):
        first_id, public_id = self.register()
        second = self.app.test_client()
        second_id, _ = self.register(second, 'owner@harbor.test', 'Harbor Electric')
        # Give the first account legitimate access to both workspaces.
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            user_id = db.execute("SELECT id FROM users WHERE email='owner@reed.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')", (second_id, user_id))
        old_token = self.csrf(self.client, '/leads/new')
        response = self.client.post('/workspace/switch', data={'csrf_token': old_token, 'workspace_id': second_id})
        self.assertEqual(response.status_code, 303)
        response = self.client.post('/leads/new', data={'csrf_token': old_token, 'customer_name': 'Wrong Company Risk', 'email': 'customer@example.test', 'service': 'HVAC', 'location': 'Austin'})
        self.assertEqual(response.status_code, 400)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0], 0)

    def test_oversized_lead_version_is_a_validation_error(self):
        _, public_id = self.register()
        lead_id = self.inquiry(public_id)
        path = f'/leads/{lead_id}'
        response = self.client.post(path, data={'csrf_token': self.csrf(self.client, path), 'status': 'Closed', 'version': '999999999999999999999999999999'})
        self.assertEqual(response.status_code, 422)
        self.assertIn(b'New', self.client.get(path).data)

    def test_opaque_preview_origin_still_requires_a_valid_csrf_token(self):
        self.app.config['ALLOW_OPAQUE_ORIGIN'] = True
        token = self.csrf(self.client, '/signup')
        response = self.client.post('/signup', data={'csrf_token': token}, headers={'Origin': 'null'})
        self.assertEqual(response.status_code, 422)  # reaches validation, never bypasses it
        self.assertEqual(self.client.post('/signup', headers={'Origin': 'null'}).status_code, 400)
        self.app.config['ALLOW_OPAQUE_ORIGIN'] = False
        self.assertEqual(self.client.post('/signup', data={'csrf_token': token}, headers={'Origin': 'null'}).status_code, 403)

    def test_expired_session_no_longer_opens_private_inbox(self):
        self.register()
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            db.execute('UPDATE sessions SET expires=0')
        response = self.client.get('/inbox')
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.location.endswith('/login'))

    def test_removed_dispatcher_cannot_read_or_write_with_an_old_form(self):
        first_id, public_id = self.register()
        lead_id = self.inquiry(public_id)
        dispatcher = self.app.test_client()
        self.register(dispatcher, 'dispatcher@harbor.test', 'Harbor Electric')
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            staff_id = db.execute("SELECT id FROM users WHERE email='dispatcher@harbor.test'").fetchone()[0]
            db.execute("INSERT INTO memberships VALUES(?,?,'dispatcher')", (first_id, staff_id))
        dispatcher.post('/workspace/switch', data={'csrf_token': self.csrf(dispatcher, '/inbox'), 'workspace_id': first_id})
        old_token = self.csrf(dispatcher, '/leads/new')
        response = self.client.post(f'/team/members/{staff_id}/remove', data={'csrf_token': self.csrf(self.client, '/team')})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(dispatcher.get(f'/leads/{lead_id}').status_code, 404)
        response = dispatcher.post('/leads/new', data={'csrf_token': old_token, 'customer_name': 'Stale staff entry', 'email': 'customer@example.test', 'service': 'HVAC', 'location': 'Austin'})
        self.assertEqual(response.status_code, 400)
        with database(Path(self.temp.name) / 'kjancy.sqlite3') as db:
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0], 1)


if __name__ == '__main__':
    unittest.main()
