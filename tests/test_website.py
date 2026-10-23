import re
import sqlite3
import tempfile
import unittest
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from itsdangerous import TimestampSigner, URLSafeTimedSerializer
from pathlib import Path

from kjancy import create_app


class WebsiteConnection(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[3] / 'work' / 'saas' / 'test-data'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.config = {'TESTING': True, 'DATA_DIR': self.temp.name, 'SECRET_KEY': 'website-test-key'}
        self.app = create_app(self.config)
        self.owner = self.app.test_client()
        self.customer = self.app.test_client()
        self.register(self.owner, 'owner@reed.test', 'Reed Home Services')
        with self.db() as db:
            self.workspace, self.public = db.execute('SELECT id,public_id FROM workspaces').fetchone()
        self.path = f'/website/{self.public}/'

    def tearDown(self):
        self.temp.cleanup()

    @contextmanager
    def db(self):
        connection = sqlite3.connect(Path(self.temp.name) / 'kjancy.sqlite3')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def token(self, client, path, name='csrf_token'):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(fr'name="{name}" value="([^"]+)"'.encode(), response.data)
        self.assertIsNotNone(match, f'{name} must be rendered into the form')
        return match[1].decode()

    def register(self, client, email, company):
        response = client.post('/signup', data={'csrf_token': self.token(client, '/signup'), 'name': 'Site Owner', 'email': email, 'company': company, 'password': 'website-test-password'})
        self.assertEqual(response.status_code, 303)

    def payload(self):
        response = self.customer.get(self.path)
        self.assertEqual(response.status_code, 200)
        hidden = dict((k.decode(), v.decode()) for k, v in re.findall(rb'name="(csrf_token|submission_token)" value="([^"]+)"', response.data))
        self.assertEqual(set(hidden), {'csrf_token', 'submission_token'})
        return {**hidden, 'name': 'Alex Cooper', 'company': 'Cooper Heating', 'email': 'alex@example.test', 'trade': 'HVAC', 'plan': 'Lead Booking System', 'message': 'Missed calls after hours.', 'website_url': ''}

    def test_website_saves_all_walkthrough_fields_in_the_correct_inbox(self):
        second = self.app.test_client()
        self.register(second, 'owner@harbor.test', 'Harbor Electric')
        with self.db() as db:
            other_id = db.execute("SELECT id FROM workspaces WHERE name='Harbor Electric'").fetchone()[0]
        payload = self.payload()
        response = self.customer.post(self.path, data={**payload, 'workspace_id': other_id, 'status': 'Closed'})
        self.assertEqual(response.status_code, 303)
        self.assertIn('/received', response.location)
        with self.db() as db:
            lead = db.execute('SELECT id,workspace_id,customer_name,business_name,email,service,support_plan,message,location,status,source FROM leads').fetchone()
        self.assertEqual(lead[1:], (self.workspace, 'Alex Cooper', 'Cooper Heating', 'alex@example.test', 'HVAC', 'Lead Booking System', 'Missed calls after hours.', '', 'New', 'website_walkthrough'))
        for value in (b'Alex Cooper', b'Cooper Heating', b'Walkthrough'):
            self.assertIn(value, self.owner.get('/inbox').data)
        detail = self.owner.get('/leads/' + lead[0])
        for value in (b'Cooper Heating', b'Lead Booking System', b'Missed calls after hours.'):
            self.assertIn(value, detail.data)
        self.assertNotIn(b'Alex Cooper', second.get('/inbox').data)
        self.assertEqual(second.get('/leads/' + lead[0]).status_code, 404)
        self.assertIn(b'Cooper Heating', self.owner.get('/inbox?q=Cooper+Heating').data)
        self.assertEqual(self.customer.get(response.location).status_code, 200)

    def test_invalid_form_preserves_safe_values_without_creating_a_lead(self):
        data = self.payload()
        for invalid in ({'email': 'wrong'}, {'company': ''}, {'trade': 'Unknown'}, {'plan': 'Unlimited'}, {'message': 'x' * 2001}):
            response = self.customer.post(self.path, data={**data, **invalid, 'name': '<script>alert(1)</script>'})
            self.assertEqual(response.status_code, 422)
            self.assertIn(b'&lt;script&gt;', response.data)
            self.assertNotIn(b'<script>alert(1)</script>', response.data)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0], 0)

    def test_replay_creates_one_lead_and_one_activity_entry(self):
        data = self.payload()
        for _ in range(2):
            self.assertEqual(self.customer.post(self.path, data=data).status_code, 303)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM lead_events').fetchone()[0], 1)

    def test_concurrent_submissions_commit_one_lead(self):
        data = self.payload()
        cookie = self.customer.get_cookie('kjancy_session').value
        clients = [self.app.test_client(), self.app.test_client()]
        for client in clients:
            client.set_cookie('kjancy_session', cookie)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda client: client.post(self.path, data=data).status_code, clients))
        self.assertEqual(results, [303, 303])
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM lead_events').fetchone()[0], 1)

    def test_expired_submission_does_not_save_a_lead(self):
        class OldTimestampSigner(TimestampSigner):
            def get_timestamp(self):
                return 1
        data = self.payload()
        serializer = URLSafeTimedSerializer('website-test-key', salt='website-walkthrough-v1')
        original = serializer.loads(data['submission_token'])
        expired = URLSafeTimedSerializer('website-test-key', salt='website-walkthrough-v1', signer=OldTimestampSigner).dumps(original)
        self.assertEqual(self.customer.post(self.path, data={**data, 'submission_token': expired}).status_code, 400)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0], 0)

    def test_rate_limit_blocks_excessive_walkthrough_posts(self):
        data = self.payload()
        for _ in range(20):
            self.assertEqual(self.customer.post(self.path, data=data).status_code, 303)
        response = self.customer.post(self.path, data=data)
        self.assertEqual(response.status_code, 429)
        self.assertIn('Retry-After', response.headers)

    def test_forged_or_cross_workspace_submission_and_bot_are_rejected(self):
        data = self.payload()
        self.assertEqual(self.customer.post(self.path, data={**data, 'csrf_token': 'x' * 64}).status_code, 400)
        self.assertEqual(self.customer.post(self.path, data={**data, 'submission_token': 'forged'}).status_code, 400)
        self.assertEqual(self.customer.post(self.path, data={**data, 'website_url': 'spam.example'}).status_code, 400)
        other = self.app.test_client()
        self.register(other, 'owner@harbor.test', 'Harbor Electric')
        with self.db() as db:
            other_public = db.execute("SELECT public_id FROM workspaces WHERE name='Harbor Electric'").fetchone()[0]
        self.assertEqual(self.customer.post(f'/website/{other_public}/', data=data).status_code, 400)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM leads').fetchone()[0], 0)

    def test_public_pages_assets_privacy_and_missing_urls(self):
        page = self.customer.get(self.path)
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Reed Home Services', page.data)
        for file in ('index.html', 'websites.html', 'lead-follow-up.html', 'dispatch-support.html', 'privacy.html', 'assets/styles.css', 'assets/app.js', 'assets/chatbot.js', 'assets/images/wall-installation.jpg'):
            with self.customer.get(self.path + file) as response:
                self.assertEqual(response.status_code, 200, file)
        privacy = self.customer.get(self.path + 'privacy.html')
        self.assertIn(b'Reed Home Services', privacy.data)
        self.assertNotIn(b'does not send it automatically', privacy.data)
        for path in (self.path + '../../README.md', self.path + 'missing.html', '/website/unknown/'):
            self.assertEqual(self.customer.get(path).status_code, 404)
        self.assertIn(self.path.encode(), self.owner.get('/inbox').data)
        self.assertEqual(self.customer.get(self.path + 'received').status_code, 303)

    def test_existing_database_is_upgraded_without_losing_leads(self):
        with self.db() as db:
            db.execute("INSERT INTO leads(id,workspace_id,customer_name,email,service,location,created,updated) VALUES('legacy',?,'Existing customer','existing@example.test','HVAC','Austin',1,1)", (self.workspace,))
            for name in ('source', 'business_name', 'support_plan', 'submission_key'):
                # SQLite removes the new index before downgrading this controlled fixture.
                for row in db.execute('PRAGMA index_list(leads)').fetchall():
                    if row[1] == 'leads_submission_key':
                        db.execute('DROP INDEX leads_submission_key')
                if name in [r[1] for r in db.execute('PRAGMA table_info(leads)')]:
                    db.execute(f'ALTER TABLE leads DROP COLUMN {name}')
        restarted = create_app(self.config)
        with self.db() as db:
            row = db.execute("SELECT customer_name,source,business_name FROM leads WHERE id='legacy'").fetchone()
        self.assertEqual(row, ('Existing customer', 'service', ''))
        self.assertEqual(restarted.test_client().get(self.path).status_code, 200)
