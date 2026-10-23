import sqlite3
import time
import uuid

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .security import digest, home_endpoint, login_endpoint, portal_mismatch, rate_limit, start_session
from .validation import email as valid_email, text

bp = Blueprint('auth', __name__)
# Unknown accounts still perform the same password verification work.
DUMMY_HASH = generate_password_hash('not-a-real-account-password', method='scrypt')


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if g.user:
        if g.user['account_kind']!='staff': return portal_mismatch('staff')
        return redirect(url_for(home_endpoint(g.user)), code=303)
    pending = session.get('pending_invite')
    invite = get_db().execute('SELECT i.*,w.name AS company FROM invitations i JOIN workspaces w ON w.id=i.workspace_id WHERE i.token_digest=? AND i.used=0 AND i.expires>?', (digest(pending), int(time.time()))).fetchone() if pending else None
    errors = {}
    values = {}
    if request.method == 'POST':
        rate_limit('signup', 10)
        for key, limit in [('name', 100), ('company', 100), ('email', 254)]:
            values[key] = text(request.form, key, limit, errors, required=key != 'company' or not invite)
        values['email'] = values['email'].lower()
        password = request.form.get('password', '')
        if not valid_email(values['email']):
            errors['email'] = 'Enter a valid email address.'
        if not 12 <= len(password) <= 128:
            errors['password'] = 'Use a password with 12 to 128 characters.'
        if invite and values['email'] != invite['email']:
            errors['email'] = 'Use the email address this invitation was sent to.'
        if not errors:
            uid, wid = uuid.uuid4().hex, uuid.uuid4().hex
            now = int(time.time())
            password_hash = generate_password_hash(password, method='scrypt')
            db = get_db()
            try:
                with db:
                    db.execute('INSERT INTO users(id,name,email,password_hash,created) VALUES(?,?,?,?,?)', (uid, values['name'], values['email'], password_hash, now))
                    if not invite:
                        import secrets
                        db.execute('INSERT INTO workspaces(id,name,public_id,created) VALUES(?,?,?,?)', (wid, values['company'], secrets.token_urlsafe(24), now))
                        db.execute('INSERT INTO memberships VALUES(?,?,?)', (wid, uid, 'owner'))
            except sqlite3.IntegrityError:
                errors['email'] = 'An account already uses this email. Sign in instead.'
            else:
                if not start_session(uid, password_hash):
                    return redirect(url_for('auth.login'), code=303)
                from .account import issue_link
                created_user = db.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
                if not issue_link(created_user, 'verify'):
                    flash('Your account was saved, but its verification message could not be prepared. Use Email verification to try again.', 'error')
                if invite:
                    session['pending_invite'] = pending
                if current_app.config['REQUIRE_EMAIL_VERIFICATION']:
                    return redirect(url_for('account.email_status'), code=303)
                if invite:
                    return redirect(url_for('workspaces.invite', token=pending), code=303)
                session['workspace_id'] = wid
                flash('Your workspace is ready. Business settings contains your public service details.', 'success')
                return redirect(url_for(home_endpoint(created_user)), code=303)
    return render_template('signup.html', title='Create your workspace', errors=errors, values=values, invite=invite), 422 if errors else 200


@bp.route('/customer/login', methods=['GET', 'POST'],endpoint='customer_login')
@bp.route('/login', methods=['GET', 'POST'])
def login():
    portal_login = request.path=='/customer/login'
    business = get_db().execute('SELECT name,public_id FROM workspaces WHERE public_id=?',(request.args['business'],)).fetchone() if portal_login and request.args.get('business') else None
    if portal_login and request.args.get('business') and not business: abort(404)
    expected_kind = 'customer' if portal_login else 'staff'
    if g.user:
        if g.user['account_kind']!=expected_kind: return portal_mismatch(expected_kind,business)
        return redirect(url_for(home_endpoint(g.user)), code=303)
    errors, values = {}, {}
    if request.method == 'POST':
        rate_limit('login', 12)
        values['email'] = request.form.get('email', '').strip().lower()[:254]
        password = request.form.get('password', '')
        user = get_db().execute('SELECT * FROM users WHERE email=?', (values['email'],)).fetchone()
        password_ok = check_password_hash(user['password_hash'] if user else DUMMY_HASH, password) if len(password) <= 128 else False
        if not user or not password_ok:
            errors['password'] = 'The email address or password does not match. Please try again.'
        elif user['account_kind']!=expected_kind:
            errors['password'] = 'Use Customer sign in for this account.' if user['account_kind']=='customer' else 'Use Admin sign in for this account.'
        else:
            pending = session.get('pending_invite')
            if not start_session(user['id'], user['password_hash']):
                errors['password'] = 'The account credentials changed. Please sign in with your current password.'
                return render_template('login.html', title='Sign in to KJAncy', errors=errors, values=values, portal_login=portal_login, customer_business=business), 422
            if user['account_kind']=='customer': pending = None
            if pending:
                session['pending_invite'] = pending
            if current_app.config['REQUIRE_EMAIL_VERIFICATION'] and user['email_verified_at'] is None:
                return redirect(url_for('account.email_status'), code=303)
            if pending:
                return redirect(url_for('workspaces.invite', token=pending), code=303)
            return redirect(url_for(home_endpoint(user)), code=303)
    return render_template('login.html', title='Customer sign in' if portal_login else 'Admin sign in', errors=errors, values=values, portal_login=portal_login, customer_business=business), 422 if errors else 200


@bp.post('/logout')
def logout():
    selected = request.form.get('portal')
    destination = ('auth.customer_login' if selected=='customer' else 'auth.login') if selected in {'admin','customer'} else login_endpoint(g.user)
    business = request.form.get('business','')[:100] if destination=='auth.customer_login' else ''
    if session.get('_sid'):
        db = get_db()
        db.execute('DELETE FROM sessions WHERE digest=?', (digest(session['_sid']),))
        db.commit()
    session.clear()
    return redirect(url_for(destination,**({'business':business} if business else {})), code=303)
