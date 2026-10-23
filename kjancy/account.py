import re
import secrets
import time

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import generate_password_hash

from .db import get_db
from .mailer import queue_email
from .security import digest, login_endpoint, rate_limit, require_login
from .validation import email as valid_email

bp = Blueprint('account', __name__)


def issue_link(user, purpose):
    now = int(time.time())
    db = get_db()
    if purpose == 'reset' and db.execute('SELECT 1 FROM account_tokens WHERE user_id=? AND purpose=? AND created>?', (user['id'], purpose, now - 60)).fetchone():
        return True
    token = secrets.token_urlsafe(32)
    expiry = now + (86400 if purpose == 'verify' else 1800)
    with db:
        db.execute('DELETE FROM account_tokens WHERE expires<?', (now - 86400,))
        db.execute('UPDATE account_tokens SET used=? WHERE user_id=? AND purpose=? AND used IS NULL', (now, user['id'], purpose))
        db.execute('INSERT INTO account_tokens(digest,user_id,purpose,email,credential_digest,created,expires) VALUES(?,?,?,?,?,?,?)', (digest(token), user['id'], purpose, user['email'], digest(user['password_hash']), now, expiry))
    endpoint = 'account.verify' if purpose == 'verify' else 'account.reset'
    link = current_app.config['PUBLIC_BASE_URL'] + url_for(endpoint, token=token)
    if purpose == 'verify':
        subject = 'Verify your KJAncy email address'
        body = f'Confirm this email address for your KJAncy account.\n\n{link}\n\nThis link expires in 24 hours and works once. Opening it does not change your account until you confirm. If you did not request it, ignore this message.'
    else:
        subject = 'Reset your KJAncy password'
        body = f'A password reset was requested for your KJAncy account.\n\n{link}\n\nThis link expires in 30 minutes and works once. Your password stays unchanged until you choose and save a new one. If you did not request it, ignore this message.'
    try:
        queue_email(current_app, user['email'], subject, body, purpose, expiry)
    except OSError:
        with db:
            db.execute('UPDATE account_tokens SET used=? WHERE digest=?', (now, digest(token)))
        current_app.logger.warning('Account message could not be queued; token invalidated.')
        return False
    return True


def valid_token(token, purpose):
    if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
        abort(410, description='This account link is invalid, expired, or already used. Request a new link.')
    item = get_db().execute('SELECT u.*,t.digest,t.credential_digest FROM account_tokens t JOIN users u ON t.user_id=u.id WHERE t.digest=? AND t.purpose=? AND t.used IS NULL AND t.expires>? AND t.email=u.email', (digest(token), purpose, int(time.time()))).fetchone()
    if not item or not secrets.compare_digest(item['credential_digest'], digest(item['password_hash'])) or (purpose == 'verify' and item['email_verified_at'] is not None):
        abort(410, description='This account link is invalid, expired, or already used. Request a new link.')
    return item


@bp.get('/account/email')
@require_login
def email_status():
    return render_template('account_email.html', title='Email verification', active='account', public_page=True)


@bp.post('/account/email/resend')
@require_login
def resend():
    rate_limit('verification-resend', 5, 3600)
    if g.user['email_verified_at'] is not None:
        flash('Your email address is already verified.', 'success')
    elif issue_link(g.user, 'verify'):
        flash('Verification message saved to the local email preview. No email was sent.' if current_app.config['MAIL_MODE'] == 'preview' else 'Verification email queued. Check your inbox shortly.', 'success')
    else:
        flash('The verification message could not be prepared. Please try again later.', 'error')
    return redirect(url_for('account.email_status'), code=303)


@bp.route('/account/verify/<token>', methods=['GET', 'POST'])
def verify(token):
    user = valid_token(token, 'verify')
    if request.method == 'POST':
        db, now = get_db(), int(time.time())
        with db:
            claimed = db.execute('UPDATE account_tokens SET used=? WHERE digest=? AND used IS NULL AND expires>?', (now, digest(token), now))
            if not claimed.rowcount:
                abort(410, description='This link was already used or expired. Request a new verification link.')
            db.execute('UPDATE users SET email_verified_at=? WHERE id=?', (now, user['id']))
            db.execute("UPDATE account_tokens SET used=? WHERE user_id=? AND purpose='verify' AND used IS NULL", (now, user['id']))
        flash('Email address verified. You can sign in to your account.', 'success')
        return redirect(url_for('account.email_status') if g.user and g.user['id'] == user['id'] else url_for(login_endpoint(user)), code=303)
    return render_template('account_verify.html', title='Verify your email', address=user['email'], public_page=True,portal_login=user['account_kind']=='customer')


@bp.route('/account/forgot-password', methods=['GET', 'POST'])
def forgot():
    errors, values = {}, {}
    portal = 'customer' if request.args.get('portal')=='customer' else 'admin'
    if request.method == 'POST':
        rate_limit('password-recovery', 8, 3600)
        values['email'] = request.form.get('email', '').strip().lower()
        if not valid_email(values['email']):
            errors['email'] = 'Enter a valid email address.'
        else:
            deadline = time.monotonic() + 0.25
            user = get_db().execute('SELECT * FROM users WHERE email=?', (values['email'],)).fetchone()
            if user:
                issue_link(user, 'reset')
            # Provider calls happen in the worker. Give the short local lookup and
            # queue operations the same response-time floor for known/unknown mail.
            remaining = deadline - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            return redirect(url_for('account.requested',**({'portal':'customer'} if portal=='customer' else {})), code=303)
    return render_template('account_forgot.html', title='Reset your password', errors=errors, values=values, public_page=True,portal_login=portal=='customer'), 422 if errors else 200


@bp.get('/account/recovery-requested')
def requested():
    return render_template('account_requested.html', title='Check your email', public_page=True,portal_login=request.args.get('portal')=='customer')


@bp.route('/account/reset/<token>', methods=['GET', 'POST'])
def reset(token):
    user = valid_token(token, 'reset')
    errors = {}
    if request.method == 'POST':
        rate_limit('password-reset', 12)
        password = request.form.get('password', '')
        if not 12 <= len(password) <= 128:
            errors['password'] = 'Use a password with 12 to 128 characters.'
        if password != request.form.get('password_confirm', ''):
            errors['password_confirm'] = 'The passwords do not match.'
        if not errors:
            hashed = generate_password_hash(password, method='scrypt')
            db, now = get_db(), int(time.time())
            with db:
                claimed = db.execute('UPDATE account_tokens SET used=? WHERE digest=? AND used IS NULL AND expires>?', (now, digest(token), now))
                if not claimed.rowcount:
                    abort(410, description='This reset link was already used or expired. Request a new one.')
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (hashed, user['id']))
                db.execute('DELETE FROM sessions WHERE user_id=?', (user['id'],))
                db.execute('UPDATE account_tokens SET used=? WHERE user_id=? AND used IS NULL', (now, user['id']))
            session.clear()
            flash('Password updated. All previous sessions were signed out. Sign in with your new password.', 'success')
            return redirect(url_for(login_endpoint(user)), code=303)
    return render_template('account_reset.html', title='Choose a new password', errors=errors, public_page=True,portal_login=user['account_kind']=='customer'), 422 if errors else 200
