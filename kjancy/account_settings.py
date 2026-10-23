"""Personal account controls; never select a user from submitted identifiers."""
import re
import time
import unicodedata

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from .db import get_db
from .security import digest, rate_limit, require_login

bp = Blueprint('account_settings',__name__)
PAGE_SIZE = 25


def active_account(db):
    actor = db.execute('SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id WHERE u.id=? AND s.digest=? AND s.expires>?',
        (g.user['id'],digest(session.get('_sid','')),int(time.time()))).fetchone()
    if actor is None:
        abort(403,description='Your session ended. Sign in again before changing your account.')
    g.user = actor
    return actor


def render_settings(errors=None,values=None,*,stale=False,code=200):
    db,now = get_db(),int(time.time())
    current = digest(session['_sid'])
    total = db.execute('SELECT count(*) FROM sessions WHERE user_id=? AND expires>?',(g.user['id'],now)).fetchone()[0]
    pages = max(1,(total+PAGE_SIZE-1)//PAGE_SIZE)
    try: page = max(1,min(int(request.args.get('page','1')),pages))
    except ValueError: page = 1
    rows = db.execute('SELECT s.expires,d.created,d.client,(s.digest=?) AS is_current FROM sessions s LEFT JOIN session_details d ON d.digest=s.digest WHERE s.user_id=? AND s.expires>? ORDER BY is_current DESC,coalesce(d.created,0) DESC,s.expires DESC,s.digest LIMIT ? OFFSET ?',
        (current,g.user['id'],now,PAGE_SIZE,(page-1)*PAGE_SIZE)).fetchall()
    return render_template('account_settings.html',title='Account settings',active='personal_account',errors=errors or {},
        values=values or {'name':g.user['name'],'profile_version':g.user['profile_version']},stale=stale,
        active_sessions=rows,total=total,page=page,pages=pages),code


def settings_response(errors,values=None,*,stale=False,code=422):
    db = get_db()
    with db:
        db.execute('BEGIN')
        active_account(db)
        return render_settings(errors,values,stale=stale,code=code)


def reauthenticate(field,errors):
    rate_limit('reauth-'+field,10)
    supplied = request.form.get(field,'')
    expected = g.user['password_hash']
    if not supplied or len(supplied)>128 or not check_password_hash(expected,supplied):
        errors[field] = 'Enter your current password to confirm this action.'
    return expected


@bp.get('/account/settings')
@require_login
def settings():
    return settings_response({},code=200)


@bp.post('/account/profile')
@require_login
def profile():
    name = request.form.get('name','').strip()
    version = request.form.get('profile_version','')
    errors = {}
    if not name or len(name)>100 or any(unicodedata.category(ch) in {'Cc','Cf'} for ch in name):
        errors['name'] = 'Enter a display name with 1 to 100 characters and no control characters.'
    if not re.fullmatch(r'[1-9]\d{0,9}',version):
        errors['form'] = 'This profile form is invalid. Reload Account settings and try again.'
    values = {'name':name,'profile_version':version}
    if errors:
        return settings_response(errors,values)
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        actor = active_account(db)
        if actor['profile_version']!=int(version):
            return render_settings({'form':'Your profile changed in another tab. Reload the latest profile before saving.'},values,stale=True,code=409)
        db.execute('UPDATE users SET name=?,profile_version=profile_version+1 WHERE id=?',(name,actor['id']))
    flash('Your display name was updated. New requests use this name.' if g.user['account_kind']=='customer' else 'Your display name was updated across your workspaces.','success')
    return redirect(url_for('account_settings.settings')+'#profile',code=303)


@bp.post('/account/password')
@require_login
def password():
    errors = {}
    expected = reauthenticate('current_password',errors)
    new = request.form.get('new_password','')
    if not 12<=len(new)<=128:
        errors['new_password'] = 'Use a password with 12 to 128 characters.'
    elif new==request.form.get('current_password',''):
        errors['new_password'] = 'Choose a password different from your current one.'
    if new!=request.form.get('password_confirm',''):
        errors['password_confirm'] = 'The new passwords do not match.'
    if errors:
        return settings_response(errors)
    hashed = generate_password_hash(new,method='scrypt')
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        actor = active_account(db)
        if actor['password_hash']!=expected:
            return render_settings({'form':'Your credentials changed. Reload and confirm your current password again.'},code=409)
        db.execute('UPDATE users SET password_hash=? WHERE id=?',(hashed,actor['id']))
        db.execute('DELETE FROM sessions WHERE user_id=?',(actor['id'],))
        db.execute('UPDATE account_tokens SET used=? WHERE user_id=? AND used IS NULL',(int(time.time()),actor['id']))
    session.clear()
    flash('Password changed. All sessions were signed out and previous account links were invalidated. Sign in with your new password.','success')
    return redirect(url_for('auth.customer_login' if actor['account_kind']=='customer' else 'auth.login'),code=303)


@bp.post('/account/sessions/revoke-others')
@require_login
def revoke_others():
    errors = {}
    expected = reauthenticate('session_password',errors)
    if errors:
        return settings_response(errors)
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        actor = active_account(db)
        if actor['password_hash']!=expected:
            return render_settings({'form':'Your credentials changed. Reload and confirm your current password again.'},code=409)
        db.execute('DELETE FROM sessions WHERE user_id=? AND digest!=?',(actor['id'],digest(session['_sid'])))
    flash('Other sessions were signed out. This session remains signed in.','success')
    return redirect(url_for('account_settings.settings')+'#sessions',code=303)
