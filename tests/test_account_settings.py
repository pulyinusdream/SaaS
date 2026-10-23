from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from contextlib import closing
from pathlib import Path
import re
import sqlite3
import time
import unittest
from unittest.mock import patch

from werkzeug.security import check_password_hash
from kjancy import create_app
import test_app as existing
from test_app import database


class AccountSettings(unittest.TestCase):
    setUp = existing.AccountsAndLeads.setUp
    tearDown = existing.AccountsAndLeads.tearDown
    csrf = existing.AccountsAndLeads.csrf
    register = existing.AccountsAndLeads.register
    original = 'a-long-test-password'

    def fixture(self):
        self.workspace,_ = self.register()
        self.assertEqual(self.client.get('/account/settings').status_code,200)
        self.path = Path(self.temp.name)/'kjancy.sqlite3'
        with database(self.path) as db:
            self.user = db.execute('SELECT id FROM users').fetchone()[0]

    def login(self,password=None,ua='Mozilla/5.0 (Windows NT 10.0) Chrome/130.0'):
        client = self.app.test_client()
        result = client.post('/login',data={'csrf_token':self.csrf(client),'email':'owner@reed.test','password':password or self.original},headers={'User-Agent':ua})
        self.assertEqual(result.status_code,303)
        return client

    def version(self,client=None):
        page = (client or self.client).get('/account/settings')
        return re.search(rb'name="profile_version" value="(\d+)"',page.data)[1].decode()

    def profile(self,name,version=None,client=None,**extra):
        client = client or self.client
        return client.post('/account/profile',data={'csrf_token':self.csrf(client,'/account/settings'),'name':name,'profile_version':version or self.version(client),**extra})

    def password(self,client=None,**extra):
        client = client or self.client
        return client.post('/account/password',data={'csrf_token':self.csrf(client,'/account/settings'),'current_password':self.original,'new_password':'new-account-test-password','password_confirm':'new-account-test-password',**extra})

    def revoke(self,client=None,**extra):
        client = client or self.client
        return client.post('/account/sessions/revoke-others',data={'csrf_token':self.csrf(client,'/account/settings'),'session_password':self.original,**extra})

    def test_profile_persists_only_own_name_and_preserves_business_records(self):
        self.fixture()
        other = self.app.test_client()
        self.register(other,'other@company.test','Other Business')
        with database(self.path) as db:
            foreign = db.execute("SELECT id FROM users WHERE email='other@company.test'").fetchone()[0]
            before = db.execute('SELECT * FROM workspaces ORDER BY id').fetchall()
        self.assertEqual(self.profile('  Morgan Reed  ',user_id=foreign,email='changed@attacker.test',workspace_id='forged').status_code,303)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT name,email,profile_version FROM users WHERE id=?',(self.user,)).fetchone(),('Morgan Reed','owner@reed.test',2))
            self.assertEqual(db.execute('SELECT name FROM users WHERE id=?',(foreign,)).fetchone()[0],'Jordan Reed')
            self.assertEqual(db.execute('SELECT * FROM workspaces ORDER BY id').fetchall(),before)
        self.assertIn(b'Morgan Reed',self.client.get('/inbox').data)

    def test_profile_invalid_values_and_stale_forms_do_not_clobber_newer_name(self):
        self.fixture()
        old = self.version()
        for name in ('','  ','x'*101,'Morgan\nReed','Morgan\u202eReed'):
            self.assertEqual(self.profile(name).status_code,422)
        for version in ('bad','0','-1','9'*100):
            self.assertEqual(self.profile('Invalid version',version=version).status_code,422)
        self.assertEqual(self.profile('Latest Name',version=old).status_code,303)
        stale = self.profile('Stale Name',version=old)
        self.assertEqual(stale.status_code,409)
        self.assertIn(b'Reload',stale.data)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT name FROM users WHERE id=?',(self.user,)).fetchone()[0],'Latest Name')

    def test_name_is_escaped_and_passwords_never_reflected_on_errors(self):
        self.fixture()
        self.profile('<script>alert(1)</script>')
        page = self.client.get('/account/settings')
        self.assertIn(b'&lt;script&gt;alert(1)&lt;/script&gt;',page.data)
        self.assertNotIn(b'<script>alert(1)</script>',page.data)
        response = self.password(current_password='private-wrong-password',new_password='private-mismatch-password')
        self.assertEqual(response.status_code,422)
        for value in (b'private-wrong-password',b'private-mismatch-password',b'new-account-test-password'):
            self.assertNotIn(value,response.data)

    def test_password_change_revokes_all_sessions_links_and_requires_new_login(self):
        self.fixture()
        second = self.login()
        cookies = [c.get_cookie('kjancy_session').value for c in (self.client,second)]
        result = self.password(user_id='forged')
        self.assertEqual(result.status_code,303)
        self.assertTrue(result.location.endswith('/login'))
        with database(self.path) as db:
            hashed,verified = db.execute('SELECT password_hash,email_verified_at FROM users WHERE id=?',(self.user,)).fetchone()
            self.assertTrue(check_password_hash(hashed,'new-account-test-password'))
            self.assertNotEqual(hashed,'new-account-test-password')
            self.assertIsNone(verified)
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE user_id=?',(self.user,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM account_tokens WHERE used IS NULL AND user_id=?',(self.user,)).fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM session_details').fetchone()[0],0)
        for cookie in cookies:
            replay = self.app.test_client()
            replay.set_cookie('kjancy_session',cookie)
            self.assertEqual(replay.get('/account/settings').status_code,303)
        self.assertEqual(self.login('new-account-test-password').get('/account/settings').status_code,200)
        old = self.app.test_client()
        self.assertEqual(old.post('/login',data={'csrf_token':self.csrf(old),'email':'owner@reed.test','password':self.original}).status_code,422)

    def test_password_validation_leaves_existing_hash_sessions_and_tokens_untouched(self):
        self.fixture()
        with database(self.path) as db:
            before = [db.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall() for table in ('users','sessions','account_tokens')]
        for extra in ({'current_password':''},{'current_password':'wrong-password'},
                      {'new_password':'short','password_confirm':'short'},
                      {'new_password':'x'*129,'password_confirm':'x'*129},
                      {'password_confirm':'mismatch-test-password'},
                      {'new_password':self.original,'password_confirm':self.original}):
            self.assertEqual(self.password(**extra).status_code,422)
        with database(self.path) as db:
            self.assertEqual([db.execute('SELECT * FROM '+table+' ORDER BY 1').fetchall() for table in ('users','sessions','account_tokens')],before)

    def test_other_session_revocation_requires_password_and_preserves_actor_foreign_user(self):
        self.fixture()
        second = self.login()
        foreign = self.app.test_client()
        self.register(foreign,'foreign@company.test','Foreign Company')
        self.assertEqual(self.revoke(session_password='wrong-password').status_code,422)
        self.assertEqual(second.get('/account/settings').status_code,200)
        self.assertEqual(self.revoke(user_id='foreign').status_code,303)
        self.assertEqual(self.client.get('/account/settings').status_code,200)
        self.assertEqual(second.get('/account/settings').status_code,303)
        self.assertEqual(foreign.get('/account/settings').status_code,200)
        self.assertEqual(self.revoke().status_code,303)
        with database(self.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions WHERE user_id=?',(self.user,)).fetchone()[0],1)
            self.assertEqual(db.execute('SELECT count(*) FROM session_details').fetchone()[0],2)

    def test_session_list_excludes_foreign_expired_and_secret_material(self):
        self.fixture()
        second = self.login()
        foreign = self.app.test_client()
        self.register(foreign,'foreign@company.test','Foreign Company')
        with database(self.path) as db:
            db.execute("INSERT INTO sessions(digest,user_id,expires) VALUES('expired-secret',?,1)",(self.user,))
            hashes = [row[0] for row in db.execute('SELECT digest FROM sessions')]
            db.execute("UPDATE session_details SET client='Foreign secret client' WHERE digest IN (SELECT digest FROM sessions WHERE user_id!=?)",(self.user,))
        response = self.client.get('/account/settings')
        self.assertIn(b'2 active sessions',response.data)
        self.assertIn(b'This session',response.data)
        self.assertNotIn(b'Foreign secret client',response.data)
        for value in hashes+[self.original]: self.assertNotIn(value.encode(),response.data)
        self.assertEqual(response.headers['Cache-Control'],'no-store')

    def test_new_session_metadata_is_bounded_and_legacy_metadata_is_honest(self):
        self.fixture()
        second = self.login(ua='Mozilla/5.0 (Windows NT 10.0) Chrome/130.0 Edg/130.0 private-ua-marker')
        with database(self.path) as db:
            created,client = db.execute('SELECT created,client FROM session_details WHERE client LIKE ?',('Edge%',)).fetchone()
            self.assertLess(abs(created-int(time.time())),10)
            self.assertEqual(client,'Edge on Windows')
            db.execute('DELETE FROM session_details')
        page = second.get('/account/settings')
        self.assertIn(b'Sign-in time unavailable',page.data)
        self.assertIn(b'Older session',page.data)
        self.assertNotIn(b'private-ua-marker',page.data)

    def test_session_pagination_retains_current_session_and_true_total(self):
        self.fixture()
        now = int(time.time())
        with database(self.path) as db:
            db.executemany('INSERT INTO sessions(digest,user_id,expires) VALUES(?,?,?)',[(f'bulk-private-{i}',self.user,now+3600+i) for i in range(28)])
        first = self.client.get('/account/settings')
        second = self.client.get('/account/settings?page=2')
        self.assertIn(b'29 active sessions',first.data)
        self.assertEqual(first.data.count(b'data-session-row'),25)
        self.assertIn(b'This session',first.data)
        self.assertEqual(second.data.count(b'data-session-row'),4)
        self.assertNotIn(b'bulk-private-',second.data)

    def test_dispatcher_unverified_and_no_workspace_can_manage_own_account(self):
        self.fixture()
        with database(self.path) as db:
            db.execute("UPDATE memberships SET role='dispatcher'")
        self.app.config['REQUIRE_EMAIL_VERIFICATION'] = True
        self.assertEqual(self.client.get('/account/settings').status_code,200)
        self.assertEqual(self.profile('Dispatcher Name').status_code,303)
        self.assertTrue(self.client.get('/inbox').location.endswith('/account/email'))
        with database(self.path) as db: db.execute('DELETE FROM memberships')
        self.assertEqual(self.client.get('/account/settings').status_code,200)
        self.assertEqual(self.revoke().status_code,303)

    def test_anonymous_csrf_and_cross_origin_requests_cannot_write(self):
        self.fixture()
        self.assertEqual(self.app.test_client().get('/account/settings').status_code,303)
        for path in ('/account/profile','/account/password','/account/sessions/revoke-others'):
            self.assertEqual(self.client.get(path).status_code,405)
            self.assertEqual(self.client.post(path,data={}).status_code,400)
            self.assertEqual(self.client.post(path,data={'csrf_token':self.csrf(self.client,'/account/settings')},headers={'Origin':'https://attacker.test'}).status_code,403)

    def test_revoked_session_after_identity_load_cannot_complete_any_write(self):
        self.fixture()
        enabled = {'value':False}
        def revoke_after_identity():
            if enabled['value']:
                with database(self.path) as db: db.execute('DELETE FROM sessions WHERE user_id=?',(self.user,))
        self.app.before_request_funcs.setdefault(None,[]).append(revoke_after_identity)
        for path,data in (('/account/profile',{'name':'Forbidden','profile_version':'1'}),
                          ('/account/password',{'current_password':self.original,'new_password':'forbidden-password','password_confirm':'forbidden-password'}),
                          ('/account/sessions/revoke-others',{'session_password':self.original})):
            client = self.login()
            data['csrf_token'] = self.csrf(client,'/account/settings')
            enabled['value'] = True
            result = client.post(path,data=data)
            enabled['value'] = False
            self.assertEqual(result.status_code,403)
        with database(self.path) as db:
            name,hashed = db.execute('SELECT name,password_hash FROM users WHERE id=?',(self.user,)).fetchone()
            self.assertEqual(name,'Jordan Reed')
            self.assertTrue(check_password_hash(hashed,self.original))

    def test_password_check_racing_a_credential_change_cannot_overwrite_it(self):
        self.fixture()
        from werkzeug.security import generate_password_hash
        replacement = generate_password_hash('concurrent-replacement-password')
        def checked_then_changed(hashed,password):
            valid = check_password_hash(hashed,password)
            with database(self.path) as db: db.execute('UPDATE users SET password_hash=? WHERE id=?',(replacement,self.user))
            return valid
        for operation in (self.password,self.revoke):
            with database(self.path) as db:
                db.execute('UPDATE users SET password_hash=? WHERE id=?',(generate_password_hash(self.original),self.user))
            with patch('kjancy.account_settings.check_password_hash',side_effect=checked_then_changed):
                self.assertEqual(operation().status_code,409)
            with database(self.path) as db:
                self.assertEqual(db.execute('SELECT password_hash FROM users WHERE id=?',(self.user,)).fetchone()[0],replacement)

    def test_concurrent_password_changes_commit_once(self):
        self.fixture()
        token = self.csrf(self.client,'/account/settings')
        cookie = self.client.get_cookie('kjancy_session').value
        clients = [self.app.test_client(),self.app.test_client()]
        for c in clients: c.set_cookie('kjancy_session',cookie)
        def post(client):
            return client.post('/account/password',data={'csrf_token':token,'current_password':self.original,'new_password':'concurrent-new-password','password_confirm':'concurrent-new-password'}).status_code
        barrier = Barrier(2)
        def synchronized_check(hashed,password):
            valid = check_password_hash(hashed,password)
            barrier.wait(timeout=10)
            return valid
        with patch('kjancy.account_settings.check_password_hash',side_effect=synchronized_check):
            with ThreadPoolExecutor(max_workers=2) as pool: statuses = list(pool.map(post,clients))
        self.assertEqual(statuses.count(303),1)
        self.assertTrue(all(status in {303,403,409} for status in statuses))
        with database(self.path) as db:
            self.assertTrue(check_password_hash(db.execute('SELECT password_hash FROM users WHERE id=?',(self.user,)).fetchone()[0],'concurrent-new-password'))
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)

    def test_reauthentication_attempts_are_persistently_rate_limited(self):
        self.fixture()
        for _ in range(10): self.assertEqual(self.revoke(session_password='incorrect-password').status_code,422)
        self.assertEqual(self.revoke().status_code,429)

    def test_migration_is_idempotent_and_backup_recovery_clears_metadata(self):
        self.fixture()
        from kjancy.backup import create_backup,restore_backup,validate_database
        config = {'TESTING':True,'DATA_DIR':self.temp.name,'SECRET_KEY':'test-signing-key'}
        create_app(config)
        create_app(config)
        self.assertEqual(self.client.get('/account/settings').status_code,200)
        archive = create_backup(self.temp.name,Path(self.temp.name)/'backups')
        restored = restore_backup(archive,Path(self.temp.name)/'recovered')
        validate_database(restored/'kjancy.sqlite3')
        with closing(sqlite3.connect(restored/'kjancy.sqlite3')) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM sessions').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT count(*) FROM session_details').fetchone()[0],0)
            self.assertEqual(db.execute('SELECT name,profile_version FROM users').fetchone(),('Jordan Reed',1))
