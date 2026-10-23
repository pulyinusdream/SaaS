from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from email import policy
from email.parser import BytesParser
from pathlib import Path
import re
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import smtplib

from kjancy import create_app


class AccountEmail(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[3] / 'work/saas/test-data'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.config = {'TESTING': True, 'DATA_DIR': self.temp.name, 'SECRET_KEY': 'account-email-test-key', 'MAIL_MODE': 'preview', 'PUBLIC_BASE_URL': 'http://127.0.0.1:4200'}
        self.app = create_app(self.config)
        self.owner = self.app.test_client()
        self.register()

    def tearDown(self):
        self.temp.cleanup()

    @contextmanager
    def db(self):
        db = sqlite3.connect(Path(self.temp.name) / 'kjancy.sqlite3')
        try:
            with db:
                yield db
        finally:
            db.close()

    def csrf(self, client, path):
        response = client.get(path)
        self.assertEqual(response.status_code, 200)
        match = re.search(rb'name="csrf_token" value="([^"]+)"', response.data)
        self.assertIsNotNone(match)
        return match[1].decode()

    def register(self):
        response = self.owner.post('/signup', data={'csrf_token': self.csrf(self.owner, '/signup'), 'name': 'Alex Reed', 'company': 'Reed Services', 'email': 'owner@reed.test', 'password': 'original-test-password'})
        self.assertEqual(response.status_code, 303)

    def mail_path(self, purpose):
        matches = []
        for file in (Path(self.temp.name) / 'mail-outbox').glob('*.eml'):
            message = BytesParser(policy=policy.default).parsebytes(file.read_bytes())
            if message['X-KJAncy-Purpose'] == purpose:
                matches.append((file, message))
        self.assertTrue(matches, f'{purpose} message must be queued')
        message = sorted(matches, key=lambda entry: entry[0].stat().st_mtime_ns)[-1][1]
        url = re.search(r'http://127\.0\.0\.1:4200(/account/[^\s]+)', message.get_content())
        self.assertIsNotNone(url)
        self.assertEqual(message['To'], 'owner@reed.test')
        return url[1]

    def request_reset(self, client=None, email='owner@reed.test'):
        client = client or self.app.test_client()
        response = client.post('/account/forgot-password', data={'csrf_token': self.csrf(client, '/account/forgot-password'), 'email': email})
        self.assertEqual(response.status_code, 303)
        return client, response

    def test_signup_queues_preview_and_get_does_not_verify_email(self):
        path = self.mail_path('verify')
        visitor = self.app.test_client()
        page = visitor.get(path)
        self.assertEqual(page.status_code, 200)
        with self.db() as db:
            self.assertIsNone(db.execute('SELECT email_verified_at FROM users').fetchone()[0])
            stored = db.execute('SELECT digest FROM account_tokens').fetchone()[0]
        self.assertNotIn(path.rsplit('/', 1)[-1], stored)
        response = visitor.post(path, data={'csrf_token': self.csrf(visitor, path)})
        self.assertEqual(response.status_code, 303)
        with self.db() as db:
            self.assertIsNotNone(db.execute('SELECT email_verified_at FROM users').fetchone()[0])
        self.assertEqual(visitor.get('/inbox').status_code, 303)
        self.assertEqual(visitor.get(path).status_code, 410)

    def test_resend_replaces_old_verification_link_and_shows_preview(self):
        old = self.mail_path('verify')
        response = self.owner.post('/account/email/resend', data={'csrf_token': self.csrf(self.owner, '/account/email')})
        self.assertEqual(response.status_code, 303)
        current = self.mail_path('verify')
        self.assertNotEqual(current, old)
        self.assertEqual(self.owner.get(old).status_code, 410)
        self.assertIn(b'Local email preview', self.owner.get('/account/email').data)

    def test_expired_wrong_purpose_and_tampered_links_do_not_change_account(self):
        verify = self.mail_path('verify')
        reset = verify.replace('/verify/', '/reset/')
        self.assertEqual(self.owner.get(reset).status_code, 410)
        self.assertEqual(self.owner.get(verify + 'x').status_code, 410)
        with self.db() as db:
            db.execute('UPDATE account_tokens SET expires=0')
        self.assertEqual(self.owner.get(verify).status_code, 410)

    def test_known_unknown_recovery_responses_match_and_no_link_is_public(self):
        first, known = self.request_reset()
        second, unknown = self.request_reset(email='unknown@example.test')
        self.assertEqual(known.location, unknown.location)
        self.assertEqual(first.get(known.location).data, second.get(unknown.location).data)
        self.assertNotIn(b'owner@reed.test', first.get(known.location).data)
        for path in ('/mail-outbox', '/account/mail-preview', '/mail-outbox/example.eml'):
            self.assertEqual(first.get(path).status_code, 404)
        self.mail_path('reset')

    def test_reset_changes_password_revokes_sessions_and_is_single_use(self):
        stale_cookie = self.owner.get_cookie('kjancy_session').value
        visitor, _ = self.request_reset()
        path = self.mail_path('reset')
        with self.db() as db:
            old_hash = db.execute('SELECT password_hash FROM users').fetchone()[0]
        response = visitor.post(path, data={'csrf_token': self.csrf(visitor, path), 'password': 'changed-test-password', 'password_confirm': 'changed-test-password'})
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.location.endswith('/login'))
        with self.db() as db:
            self.assertNotEqual(db.execute('SELECT password_hash FROM users').fetchone()[0], old_hash)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM account_tokens WHERE used IS NULL').fetchone()[0], 0)
            self.assertIsNone(db.execute('SELECT email_verified_at FROM users').fetchone()[0])
        replay = self.app.test_client()
        replay.set_cookie('kjancy_session', stale_cookie)
        self.assertEqual(replay.get('/inbox').status_code, 303)
        self.assertEqual(visitor.get(path).status_code, 410)
        self.assertEqual(visitor.get('/inbox').status_code, 303)
        for password, expected in [('original-test-password', 422), ('changed-test-password', 303)]:
            self.assertEqual(visitor.post('/login', data={'csrf_token': self.csrf(visitor, '/login'), 'email': 'owner@reed.test', 'password': password}).status_code, expected)

    def test_invalid_password_does_not_consume_link_and_never_echoes_password(self):
        visitor, _ = self.request_reset()
        path = self.mail_path('reset')
        for password, confirmation in [('short', 'short'), ('long-test-password', 'different')]:
            response = visitor.post(path, data={'csrf_token': self.csrf(visitor, path), 'password': password, 'password_confirm': confirmation})
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(f'value="{password}"'.encode(), response.data)
        self.assertEqual(visitor.get(path).status_code, 200)

    def test_reset_and_verification_need_csrf_and_email_binding(self):
        path = self.mail_path('verify')
        self.assertEqual(self.owner.post(path).status_code, 400)
        with self.db() as db:
            db.execute("UPDATE users SET email='changed@reed.test'")
        self.assertEqual(self.owner.get(path).status_code, 410)
        self.assertEqual(self.owner.post('/account/forgot-password').status_code, 400)

    def test_preview_does_not_lock_existing_flow_but_strict_mode_does(self):
        self.assertEqual(self.owner.get('/inbox').status_code, 200)
        self.assertIn(b'Email not verified', self.owner.get('/inbox').data)
        self.app.config['REQUIRE_EMAIL_VERIFICATION'] = True
        self.assertTrue(self.owner.get('/inbox').location.endswith('/account/email'))
        self.assertTrue(self.owner.get('/team').location.endswith('/account/email'))
        self.assertTrue(self.owner.get('/workspaces').location.endswith('/account/email'))
        self.assertEqual(self.owner.get('/account/email').status_code, 200)
        path = self.mail_path('verify')
        self.owner.post(path, data={'csrf_token': self.csrf(self.owner, path)})
        self.assertEqual(self.owner.get('/inbox').status_code, 200)

    def test_concurrent_reset_claims_only_allow_one_change(self):
        visitor, _ = self.request_reset()
        path = self.mail_path('reset')
        csrf = self.csrf(visitor, path)
        cookie = visitor.get_cookie('kjancy_session').value
        clients = [self.app.test_client(), self.app.test_client()]
        for client in clients:
            client.set_cookie('kjancy_session', cookie)
        def post(client):
            return client.post(path, data={'csrf_token': csrf, 'password': 'concurrent-test-password', 'password_confirm': 'concurrent-test-password'}).status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(post, clients)), [303, 410])

    def test_missing_smtp_and_public_preview_configuration_fail_closed(self):
        for extra in ({'MAIL_MODE': 'smtp'}, {'PUBLIC_BASE_URL': 'https://example.test'}, {'PUBLIC_BASE_URL': 'http://evil.test'}, {'MAIL_MODE': 'plaintext'}):
            with self.assertRaises(ValueError):
                create_app({**self.config, **extra})

    def test_login_using_a_stale_password_check_cannot_survive_reset(self):
        from werkzeug.security import check_password_hash
        visitor, _ = self.request_reset()
        reset_path = self.mail_path('reset')
        reset_csrf = self.csrf(visitor, reset_path)
        login = self.app.test_client()
        login_csrf = self.csrf(login, '/login')
        def checked_then_reset(hashed, password):
            valid = check_password_hash(hashed, password)
            result = visitor.post(reset_path, data={'csrf_token': reset_csrf, 'password': 'replacement-test-password', 'password_confirm': 'replacement-test-password'})
            self.assertEqual(result.status_code, 303)
            return valid
        # Pause only the real password check's return to reproduce the interleave.
        with patch('kjancy.auth.check_password_hash', side_effect=checked_then_reset):
            response = login.post('/login', data={'csrf_token': login_csrf, 'email': 'owner@reed.test', 'password': 'original-test-password'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(login.get('/inbox').status_code, 303)
        with self.db() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)

    def test_permanent_recipient_failure_does_not_block_later_mail(self):
        from kjancy.mailer import deliver_pending, queue_email
        import time
        outbox = Path(self.app.config['MAIL_OUTBOX'])
        for file in outbox.glob('*.eml'):
            file.unlink()
        queue_email(self.app, 'invalid@example.test', 'Bad recipient', 'test', 'verify', int(time.time()) + 3600)
        queue_email(self.app, 'valid@example.test', 'Good recipient', 'test', 'verify', int(time.time()) + 3600)
        class LocalSMTPBoundary:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def ehlo(self): pass
            def starttls(self, **kwargs): pass
            def login(self, *args): pass
            def send_message(self, message):
                if message['To'] == 'invalid@example.test':
                    raise smtplib.SMTPRecipientsRefused({'invalid@example.test': (550, b'No such mailbox')})
                return {}
        self.app.config.update(MAIL_MODE='smtp', SMTP_HOST='smtp.example.test', SMTP_USERNAME='test', SMTP_PASSWORD='test')
        # SMTP is an unavailable external boundary; queue lifecycle stays real.
        with patch('kjancy.mailer.smtplib.SMTP', LocalSMTPBoundary):
            deliver_pending(self.app)
        self.assertEqual(list(outbox.glob('*.eml')), [])
        self.assertEqual(len(list(outbox.glob('*.failed'))), 1)

    def test_legacy_user_upgrade_preserves_credentials_and_does_not_fake_verification(self):
        with self.db() as db:
            before = db.execute('SELECT id,email,password_hash FROM users').fetchone()
            db.execute('ALTER TABLE users DROP COLUMN email_verified_at')
        create_app(self.config)
        with self.db() as db:
            after = db.execute('SELECT id,email,password_hash,email_verified_at FROM users').fetchone()
        self.assertEqual(after[:3], before)
        self.assertIsNone(after[3])

    def test_tls_failure_retains_mail_without_authentication_or_plaintext_fallback(self):
        from kjancy.mailer import deliver_pending
        outbox = Path(self.app.config['MAIL_OUTBOX'])
        class RefusesTLS:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def ehlo(self): pass
            def starttls(self, **kwargs):
                raise smtplib.SMTPNotSupportedError('STARTTLS unavailable')
            def login(self, *args):
                raise AssertionError('Credentials must never be sent before TLS succeeds')
            def send_message(self, *args):
                raise AssertionError('Message must never be sent without TLS')
        self.app.config.update(MAIL_MODE='smtp', SMTP_HOST='smtp.example.test', SMTP_USERNAME='test', SMTP_PASSWORD='test')
        with patch('kjancy.mailer.smtplib.SMTP', RefusesTLS):
            deliver_pending(self.app)
        self.assertEqual(len(list(outbox.glob('*.eml'))), 1)

    def test_temporary_recipient_retries_rotate_behind_newer_mail(self):
        from kjancy.mailer import deliver_pending, queue_email
        import time
        outbox = Path(self.app.config['MAIL_OUTBOX'])
        for file in outbox.glob('*.eml'):
            file.unlink()
        for number in range(20):
            queue_email(self.app, f'busy{number}@example.test', 'Temporary rejection', 'test', 'verify', int(time.time()) + 3600)
        queue_email(self.app, 'healthy@example.test', 'Healthy mailbox', 'test', 'verify', int(time.time()) + 3600)
        class TemporaryRecipient:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def ehlo(self): pass
            def starttls(self, **kwargs): pass
            def login(self, *args): pass
            def send_message(self, message):
                if message['To'].startswith('busy'):
                    raise smtplib.SMTPRecipientsRefused({message['To']: (450, b'Try later')})
                return {}
        self.app.config.update(MAIL_MODE='smtp', SMTP_HOST='smtp.example.test', SMTP_USERNAME='test', SMTP_PASSWORD='test')
        with patch('kjancy.mailer.smtplib.SMTP', TemporaryRecipient):
            deliver_pending(self.app)
            deliver_pending(self.app)
        remaining = [BytesParser(policy=policy.default).parsebytes(file.read_bytes())['To'] for file in outbox.glob('*.eml')]
        self.assertEqual(len(remaining), 20)
        self.assertNotIn('healthy@example.test', remaining)

    def test_concurrent_expiry_cleanup_does_not_crash_delivery(self):
        from kjancy.mailer import deliver_pending
        outbox = Path(self.app.config['MAIL_OUTBOX'])
        candidate = next(outbox.glob('*.eml'))
        original_stat = Path.stat
        removed = False
        def deleted_before_stat(file, *args, **kwargs):
            nonlocal removed
            if file == candidate and not removed:
                removed = True
                file.unlink()
            return original_stat(file, *args, **kwargs)
        self.app.config['MAIL_MODE'] = 'smtp'
        with patch.object(Path, 'stat', deleted_before_stat):
            deliver_pending(self.app)
        self.assertTrue(removed)
        self.assertEqual(list(outbox.glob('*.eml')), [])
