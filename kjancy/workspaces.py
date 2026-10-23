import secrets
import time
import uuid

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for

from .db import get_db
from . import appointments
from .security import digest, owner_only, rate_limit, require_login, require_staff, require_workspace
from .validation import email as valid_email

bp = Blueprint('workspaces', __name__)


@bp.get('/workspaces')
@require_staff
def choose():
    return render_template('workspaces.html', title='Your workspaces', active='workspaces')


@bp.post('/workspace/switch')
@require_staff
def switch():
    workspace = get_db().execute('SELECT workspace_id FROM memberships WHERE user_id=? AND workspace_id=?', (g.user['id'], request.form.get('workspace_id', ''))).fetchone()
    if not workspace:
        abort(404)
    session['workspace_id'] = workspace['workspace_id']
    return redirect(url_for('leads.inbox'), code=303)


@bp.get('/team')
@require_workspace
def team():
    members = get_db().execute('SELECT u.id,u.name,u.email,m.role FROM users u JOIN memberships m ON u.id=m.user_id WHERE m.workspace_id=? ORDER BY m.role DESC,u.name', (g.workspace['id'],)).fetchall()
    invites = []
    new_invite = None
    if g.workspace['role'] == 'owner':
        invites = get_db().execute('SELECT * FROM invitations WHERE workspace_id=? AND used=0 AND expires>? ORDER BY created DESC', (g.workspace['id'], int(time.time()))).fetchall()
        candidate = session.get('new_invite')
        if candidate and candidate['workspace_id'] == g.workspace['id'] and any(i['id'] == candidate['id'] for i in invites):
            new_invite = candidate
    return render_template('team.html', title='Team access', members=members, invitations=invites, new_invite=new_invite, active='team', errors={})


@bp.post('/team/invite')
@require_workspace
def create_invite():
    owner_only()
    rate_limit('invite', 30)
    address = request.form.get('email', '').strip().lower()
    if not valid_email(address):
        flash('Enter a valid email address for the invitation.', 'error')
        return redirect(url_for('workspaces.team'), code=303)
    db = get_db()
    exists = db.execute('SELECT 1 FROM memberships m JOIN users u ON m.user_id=u.id WHERE m.workspace_id=? AND u.email=?', (g.workspace['id'], address)).fetchone()
    if exists:
        flash('This person already has access to this workspace.', 'error')
        return redirect(url_for('workspaces.team'), code=303)
    token, uid, now = secrets.token_urlsafe(32), uuid.uuid4().hex, int(time.time())
    with db:
        db.execute('UPDATE invitations SET used=1 WHERE workspace_id=? AND email=? AND used=0', (g.workspace['id'], address))
        db.execute('INSERT INTO invitations(id,workspace_id,email,token_digest,expires,created) VALUES(?,?,?,?,?,?)', (uid, g.workspace['id'], address, digest(token), now + 86400, now))
    session['new_invite'] = {'id': uid, 'token': token, 'workspace_id': g.workspace['id']}
    flash('Invitation link created. Copy it and share it with the invited person. No email has been sent.', 'success')
    return redirect(url_for('workspaces.team'), code=303)


@bp.post('/team/invites/<invitation_id>/revoke')
@require_workspace
def revoke_invite(invitation_id):
    owner_only()
    db = get_db()
    result = db.execute('UPDATE invitations SET used=1 WHERE id=? AND workspace_id=? AND used=0', (invitation_id, g.workspace['id']))
    db.commit()
    if not result.rowcount:
        abort(404)
    flash('Invitation revoked.', 'success')
    return redirect(url_for('workspaces.team'), code=303)


@bp.post('/team/members/<user_id>/remove')
@require_workspace
def remove_member(user_id):
    owner_only()
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        result = db.execute("DELETE FROM memberships WHERE workspace_id=? AND user_id=? AND role='dispatcher'", (g.workspace['id'], user_id))
        if not result.rowcount:
            abort(404)
        affected = db.execute('SELECT id FROM leads WHERE workspace_id=? AND assigned_user_id=?', (g.workspace['id'], user_id)).fetchall()
        now = int(time.time())
        db.execute('UPDATE leads SET assigned_user_id=NULL,version=version+1,updated=? WHERE workspace_id=? AND assigned_user_id=?', (now,g.workspace['id'],user_id))
        for lead in affected:
            db.execute('INSERT INTO lead_events(lead_id,workspace_id,actor,description,created) VALUES(?,?,?,?,?)', (lead['id'],g.workspace['id'],g.user['name'],'Unassigned because dispatcher access was removed',now))
        appointments.release_member(db,user_id,{lead['id'] for lead in affected})
    flash('Dispatcher access removed. They can no longer open this workspace.', 'success')
    return redirect(url_for('workspaces.team'), code=303)


@bp.route('/invite/<token>', methods=['GET', 'POST'])
def invite(token):
    if g.user and g.user['account_kind']=='customer':
        abort(403,description='Staff invitations cannot be accepted by customer accounts.')
    db = get_db()
    item = db.execute('SELECT i.*,w.name AS company FROM invitations i JOIN workspaces w ON i.workspace_id=w.id WHERE token_digest=?', (digest(token),)).fetchone()
    if not item or item['used'] or item['expires'] <= int(time.time()):
        abort(410)
    if not g.user:
        session['pending_invite'] = token
    if request.method == 'POST':
        if not g.user:
            return redirect(url_for('auth.login'), code=303)
        if current_app.config.get('REQUIRE_EMAIL_VERIFICATION') and g.user['email_verified_at'] is None:
            session['pending_invite'] = token
            return redirect(url_for('account.email_status'), code=303)
        if g.user['email'] != item['email']:
            abort(403, description='Sign in with the email address named in the invitation.')
        with db:
            # The claim and membership insert commit together; token reuse loses the conditional update.
            claimed = db.execute('UPDATE invitations SET used=1 WHERE id=? AND used=0 AND expires>?', (item['id'], int(time.time())))
            if not claimed.rowcount:
                abort(410)
            db.execute("INSERT OR IGNORE INTO memberships(workspace_id,user_id,role) VALUES(?,?,'dispatcher')", (item['workspace_id'], g.user['id']))
        session['workspace_id'] = item['workspace_id']
        session.pop('pending_invite', None)
        flash('You now have dispatcher access to this workspace.', 'success')
        return redirect(url_for('leads.inbox'), code=303)
    return render_template('invite.html', title='Join a workspace', invitation=item)
