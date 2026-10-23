from contextlib import closing
from pathlib import Path
import hashlib
import importlib
import json
import secrets
import sqlite3
import tempfile
import unittest
import zipfile

from kjancy import create_app


class Operations(unittest.TestCase):
    def setUp(self):
        parent = Path(__file__).resolve().parents[3] / 'work/saas/test-data'
        parent.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=parent)
        self.root = Path(self.temp.name)
        self.source = self.root / 'data'
        self.app = create_app({'TESTING': True, 'DATA_DIR': str(self.source)})
        with closing(sqlite3.connect(self.source / 'kjancy.sqlite3')) as db, db:
            db.execute("INSERT INTO users(id,name,email,password_hash,created) VALUES('u','Test owner','owner@example.test','existing-hash',1)")
            db.execute("INSERT INTO workspaces(id,name,public_id,created) VALUES('w','Test business','public-token',1)")
            db.execute("INSERT INTO memberships VALUES('w','u','owner')")
            db.execute("INSERT INTO sessions VALUES('old-session','u',9999999999)")
            db.execute("INSERT INTO account_tokens VALUES('old-token','u','reset','owner@example.test','old-credential',1,9999999999,NULL)")
            db.execute("INSERT INTO invitations(id,workspace_id,email,token_digest,expires,created) VALUES('invite','w','other@example.test','old-invite',9999999999,1)")
        self.env = {'KJANCY_DATA_DIR': str(self.root / 'production-data'), 'KJANCY_PUBLIC_BASE_URL': 'https://pilot.example.test',
                    'KJANCY_MAIL_MODE': 'smtp', 'KJANCY_MAIL_FROM': 'sender@example.test', 'KJANCY_SMTP_HOST': 'smtp.example.test',
                    'KJANCY_SMTP_USERNAME': 'smtp-user', 'KJANCY_SMTP_PASSWORD': secrets.token_urlsafe(24), 'KJANCY_TRUSTED_PROXY': '127.0.0.1'}

    def tearDown(self):
        self.temp.cleanup()

    def operations(self):
        return importlib.import_module('kjancy.backup')

    def deployment(self):
        return importlib.import_module('kjancy.deployment')

    def test_backup_includes_committed_wal_data_without_stopping_the_writer(self):
        module = self.operations()
        with closing(sqlite3.connect(self.source / 'kjancy.sqlite3')) as live:
            live.execute('PRAGMA wal_autocheckpoint=0')
            live.execute("INSERT INTO leads(id,workspace_id,customer_name,service,location,created,updated) VALUES('lead','w','WAL customer','HVAC','Austin',1,1)")
            live.commit()
            archive = module.create_backup(self.source, self.root / 'backups')
            self.assertTrue(live.execute('SELECT count(*) FROM leads').fetchone()[0])
            report = module.verify_backup(archive)
            self.assertEqual(report['format'], 1)
            restored = module.restore_backup(archive, self.root / 'restored')
        with closing(sqlite3.connect(restored / 'kjancy.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT customer_name FROM leads').fetchone()[0], 'WAL customer')
            self.assertEqual(db.execute('SELECT email,password_hash FROM users').fetchone(), ('owner@example.test', 'existing-hash'))

    def test_restore_rotates_key_and_revokes_sessions_tokens_and_invitations(self):
        module = self.operations()
        archive = module.create_backup(self.source, self.root / 'backups')
        with zipfile.ZipFile(archive) as bundle:
            self.assertEqual(set(bundle.namelist()), {'manifest.json', 'kjancy.sqlite3'})
        restored = module.restore_backup(archive, self.root / 'restored')
        self.assertNotEqual((restored / 'session.key').read_bytes(), (self.source / 'session.key').read_bytes())
        with closing(sqlite3.connect(restored / 'kjancy.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT count(*) FROM account_tokens').fetchone()[0], 0)
            self.assertEqual(db.execute('SELECT used FROM invitations').fetchone()[0], 1)
            self.assertEqual(db.execute('SELECT count(*) FROM memberships').fetchone()[0], 1)
        with closing(sqlite3.connect(self.source / 'kjancy.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0], 1)

    def test_restore_never_overwrites_existing_or_published_data(self):
        module = self.operations()
        archive = module.create_backup(self.source, self.root / 'backups')
        before = (self.source / 'kjancy.sqlite3').read_bytes()
        with self.assertRaises(ValueError):
            module.restore_backup(archive, self.source)
        self.assertEqual((self.source / 'kjancy.sqlite3').read_bytes(), before)
        app_root = Path(__file__).resolve().parents[1]
        for target in (app_root / 'restore-test', app_root / 'marketing/restore-test'):
            with self.assertRaises(ValueError):
                module.restore_backup(archive, target)
            self.assertFalse(target.exists())

    def test_corrupt_or_unexpected_archive_is_rejected_before_creating_destination(self):
        module = self.operations()
        archive = module.create_backup(self.source, self.root / 'backups')
        with zipfile.ZipFile(archive) as source:
            manifest, payload = source.read('manifest.json'), source.read('kjancy.sqlite3')
        cases = (
            {'manifest.json': manifest, 'kjancy.sqlite3': payload + b'corrupt'},
            {'manifest.json': manifest, '../kjancy.sqlite3': payload},
            {'manifest.json': b'{}', 'kjancy.sqlite3': b'not SQLite'},
            {'manifest.json': manifest, 'kjancy.sqlite3': payload, 'session.key': b'secret'},
        )
        for number, files in enumerate(cases):
            altered = self.root / f'bad-{number}.zip'
            with zipfile.ZipFile(altered, 'w') as bundle:
                for name, data in files.items(): bundle.writestr(name, data)
            with self.assertRaises(ValueError):
                module.restore_backup(altered, self.root / f'target-{number}')
            self.assertFalse((self.root / f'target-{number}').exists())

    def test_production_settings_require_explicit_safe_hosting_configuration(self):
        module = self.deployment()
        config, server = module.production_settings(self.env)
        self.assertTrue(config['SESSION_COOKIE_SECURE'])
        self.assertTrue(config['ENFORCE_HTTPS'])
        self.assertFalse(config['ALLOW_OPAQUE_ORIGIN'])
        self.assertEqual(config['TRUSTED_HOSTS'], ['pilot.example.test'])
        self.assertEqual(server['trusted_proxy'], '127.0.0.1')
        self.assertEqual(server['trusted_proxy_headers'], {'x-forwarded-for', 'x-forwarded-proto'})
        self.assertFalse((self.root / 'production-data').exists())
        for host in ('https://.example.test', 'https://pilot..example.test'):
            with self.subTest(host=host), self.assertRaises(ValueError):
                module.production_settings({**self.env, 'KJANCY_PUBLIC_BASE_URL': host})
        for overrides in ({'KJANCY_MAIL_MODE':'preview'}, {'KJANCY_PUBLIC_BASE_URL':'http://pilot.example.test'}, {'KJANCY_TRUSTED_PROXY':'*'}, {'KJANCY_DATA_DIR':'relative'}, {'KJANCY_SMTP_PASSWORD':''}, {'KJANCY_PUBLIC_BASE_URL':'https://user:pass@pilot.example.test'}, {'KJANCY_PUBLIC_BASE_URL':'https://pilot.example.test/path'}, {'PORT':'0'}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                module.production_settings({**self.env, **overrides})

    def test_production_https_gate_does_not_accept_insecure_credentials(self):
        module = self.deployment()
        config, _ = module.production_settings(self.env)
        app = create_app({**config, 'TESTING': True})
        client = app.test_client()
        self.assertEqual(client.get('/login', base_url='http://pilot.example.test').status_code, 308)
        self.assertEqual(client.post('/login', base_url='http://pilot.example.test', data={'email':'owner@example.test','password':'ignored'}).status_code, 400)
        self.assertEqual(client.get('/health', base_url='http://pilot.example.test').status_code, 200)
        self.assertEqual(client.get('/login', base_url='https://pilot.example.test').status_code, 200)
        self.assertEqual(client.get('/login', base_url='https://untrusted.example.test').status_code, 400)
        self.assertTrue(client.get_cookie('kjancy_session', domain='pilot.example.test').secure)
