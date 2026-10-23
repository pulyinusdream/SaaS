import hashlib
import hmac
import re
import secrets
import time
from functools import wraps
from urllib.parse import urlsplit

from flask import abort, current_app, g, redirect, render_template, request, session, url_for

from .db import get_db

SESSION_SECONDS = 8 * 60 * 60


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_urlsafe(32)
    workspace = getattr(g, 'workspace', None)
    context = workspace['id'] if workspace else 'public'
    key = current_app.secret_key
    if isinstance(key, str):
        key = key.encode('utf-8')
    # Bind the form to the company it was rendered for. A different tab changing
    # the shared session's workspace must never redirect a write to another tenant.
    return hmac.new(key, f'{session["_csrf"]}:{context}'.encode('utf-8'), hashlib.sha256).hexdigest()


def client_label():
    """A hint from an allowlist, never raw client input or a verified device."""
    ua = request.headers.get('User-Agent','')[:1000]
    browser = next((label for marker,label in (('Edg/','Edge'),('EdgiOS/','Edge'),('EdgA/','Edge'),('Firefox/','Firefox'),('FxiOS/','Firefox'),('Chrome/','Chrome'),('CriOS/','Chrome'),('Safari/','Safari')) if marker in ua),'Unrecognized browser')
    platform = next((label for marker,label in (('Android','Android'),('iPhone','iOS'),('iPad','iPadOS'),('Windows','Windows'),('Macintosh','macOS'),('Linux','Linux')) if marker in ua),'')
    return browser+(' on '+platform if platform else '')


def start_session(user_id, expected_password_hash):
    db = get_db()
    previous = session.get('_sid')
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    with db:
        # The credential decision and session insertion share one SQLite write.
        # A reset either deletes this session afterwards or changes the hash first,
        # in which case a stale in-flight password check cannot create a session.
        inserted = db.execute('INSERT INTO sessions(digest,user_id,expires) SELECT ?,id,? FROM users WHERE id=? AND password_hash=?', (digest(token), now + SESSION_SECONDS, user_id, expected_password_hash))
        if not inserted.rowcount:
            return False
        db.execute('INSERT INTO session_details(digest,created,client) VALUES(?,?,?)',(digest(token),now,client_label()))
        if previous:
            db.execute('DELETE FROM sessions WHERE digest=?', (digest(previous),))
        db.execute('DELETE FROM sessions WHERE expires<?', (now,))
    session.clear()
    session['_sid'] = token
    session.permanent = True
    csrf_token()
    return True


def require_login(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for('auth.customer_login' if request.blueprint=='customers' else 'auth.login'), code=303)
        if (current_app.config.get('REQUIRE_EMAIL_VERIFICATION') and g.user['email_verified_at'] is None
                and request.endpoint not in {'account.email_status', 'account.resend', 'account_settings.settings',
                    'account_settings.profile', 'account_settings.password', 'account_settings.revoke_others'}):
            return redirect(url_for('account.email_status'), code=303)
        return view(*args, **kwargs)
    return wrapped


def require_workspace(view):
    @wraps(view)
    @require_login
    def wrapped(*args, **kwargs):
        if g.user['account_kind']=='customer':
            abort(403,description='Customer accounts cannot access business administration.')
        if g.workspace is None:
            return redirect(url_for('workspaces.choose'), code=303)
        return view(*args, **kwargs)
    return wrapped


def home_endpoint(user):
    return 'customers.home' if user and user['account_kind']=='customer' else ('leads.inbox' if user else 'auth.signup')


def login_endpoint(user):
    return 'auth.customer_login' if user and user['account_kind']=='customer' else 'auth.login'


def portal_mismatch(expected,business=None):
    """Never silently reuse a signed-in account in the other role's entry flow."""
    return render_template('portal_mismatch.html',title='Choose the correct account',
                           expected_kind=expected,business=business,home=home_endpoint(g.user),
                           public_page=True,portal_login=expected=='customer'),403


def require_staff(view):
    @wraps(view)
    @require_login
    def wrapped(*args,**kwargs):
        if g.user['account_kind']!='staff': abort(403,description='This area is for business staff.')
        return view(*args,**kwargs)
    return wrapped


def owner_only():
    if not g.workspace or g.workspace['role'] != 'owner':
        abort(403, description='Only the workspace owner can manage team access.')


def rate_limit(action, limit, seconds=900):
    # No forwarded headers are trusted. Waitress runs directly on loopback.
    key = digest(f'{action}:{request.remote_addr or "unknown"}')
    now = int(time.time())
    db = get_db()
    db.execute('DELETE FROM rate_limits WHERE expires<?', (now,))
    db.execute('INSERT INTO rate_limits(bucket,count,expires) VALUES(?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1', (key, now + seconds))
    count = db.execute('SELECT count FROM rate_limits WHERE bucket=?', (key,)).fetchone()['count']
    db.commit()
    if count > limit:
        abort(429, description='Too many attempts. Please wait a few minutes and try again.')


def init_app(app):
    @app.before_request
    def load_identity_and_check_writes():
        g.user, g.workspace, g.memberships, g.customer = None, None, [], None
        if current_app.config.get('ENFORCE_HTTPS') and not request.is_secure and request.endpoint != 'health':
            if request.method in {'GET', 'HEAD'}:
                target = current_app.config['PUBLIC_BASE_URL'] + request.full_path.rstrip('?')
                return redirect(target, code=308)
            abort(400, description='Use the secure HTTPS address before submitting account details.')
        sid = session.get('_sid')
        if sid:
            g.user = get_db().execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.digest=? AND s.expires>?', (digest(sid), int(time.time()))).fetchone()
            if g.user:
                if g.user['account_kind']=='customer':
                    g.customer = get_db().execute('SELECT c.*,w.name AS business_name,w.public_id FROM customer_accounts c JOIN workspaces w ON w.id=c.workspace_id WHERE c.user_id=?',(g.user['id'],)).fetchone()
                else:
                    g.memberships = get_db().execute('SELECT w.*,m.role FROM workspaces w JOIN memberships m ON m.workspace_id=w.id WHERE m.user_id=? ORDER BY w.created,w.id', (g.user['id'],)).fetchall()
                    selected = session.get('workspace_id')
                    g.workspace = next((w for w in g.memberships if w['id'] == selected), None)
                    if g.workspace is None and g.memberships:
                        g.workspace = g.memberships[0]
                        session['workspace_id'] = g.workspace['id']
            else:
                session.clear()
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            origin = request.headers.get('Origin')
            if origin:
                parsed = urlsplit(origin)
                opaque_local_preview = (origin == 'null' and current_app.config.get('ALLOW_OPAQUE_ORIGIN', False)
                                        and urlsplit(request.host_url).hostname in {'127.0.0.1', 'localhost', '::1'})
                if not opaque_local_preview and (parsed.scheme != request.scheme or parsed.netloc != request.host):
                    current_app.logger.warning('Rejected cross-origin form: origin=%r host=%r scheme=%r', origin, request.host, request.scheme)
                    abort(403, description='This request came from a different website. Reopen the form and try again.')
            supplied = request.form.get('csrf_token', '')
            expected = csrf_token() if session.get('_csrf') else ''
            if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', supplied) or not expected or not secrets.compare_digest(expected, supplied):
                abort(400, description='The form expired or could not be verified. Reopen the page and try again.')

    @app.after_request
    def security_headers(response):
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'
        if request.endpoint != 'static':
            response.headers['Cache-Control'] = 'no-store'
        if request.is_secure:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000'
        if response.status_code == 429:
            response.headers['Retry-After'] = '900'
        return response

    app.jinja_env.globals['csrf_token'] = csrf_token
