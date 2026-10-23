"""Workspace-scoped assignments and one current follow-up per inquiry."""
from datetime import datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo, available_timezones

from flask import Blueprint, abort, flash, g, redirect, request, url_for

from .db import get_db
from .security import owner_only, require_workspace

bp = Blueprint('followups', __name__)
TIMEZONES = tuple(sorted(available_timezones()))
PENDING = "l.followup_due IS NOT NULL AND l.followup_completed_at IS NULL AND l.status!='Closed'"
ASSIGNEE_JOIN = 'LEFT JOIN memberships am ON am.workspace_id=l.workspace_id AND am.user_id=l.assigned_user_id LEFT JOIN users au ON au.id=am.user_id'


def utc_now():
    return datetime.now(timezone.utc)


def format_due(value, zone='UTC'):
    if value is None:
        return ''
    return datetime.fromtimestamp(value, ZoneInfo(zone)).strftime('%b %d, %Y at %H:%M %Z')


def parse_due(value, zone):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}', value):
        raise ValueError('Enter a valid due date and time.')
    try:
        local = datetime.strptime(value, '%Y-%m-%dT%H:%M')
        if not 2000 <= local.year <= 2100:
            raise ValueError()
    except ValueError as error:
        raise ValueError('Choose a date between 2000 and 2100.') from error
    tz = ZoneInfo(zone)
    candidates = set()
    for fold in (0, 1):
        aware = local.replace(tzinfo=tz, fold=fold)
        instant = aware.timestamp()
        if datetime.fromtimestamp(instant, tz).replace(tzinfo=None) == local:
            candidates.add(int(instant))
    if not candidates:
        raise ValueError('This local time is skipped by a clock change. Choose another time.')
    if len(candidates) > 1:
        raise ValueError('This local time occurs twice during a clock change. Choose an unambiguous time.')
    return candidates.pop()


def queue_views():
    now = utc_now()
    today = now.astimezone(ZoneInfo(g.workspace['timezone'])).date()
    start = datetime.combine(today, datetime.min.time(), ZoneInfo(g.workspace['timezone']))
    end = datetime.combine(today + timedelta(days=1), datetime.min.time(), ZoneInfo(g.workspace['timezone']))
    return {
        'all': ('All leads', '1=1', []),
        'mine': ('My leads', 'am.user_id=?', [g.user['id']]),
        'unassigned': ('Unassigned', 'am.user_id IS NULL', []),
        'today': ('Due today', PENDING + ' AND l.followup_due>=? AND l.followup_due<?', [int(start.timestamp()), int(end.timestamp())]),
        'overdue': ('Overdue', PENDING + ' AND l.followup_due<?', [int(now.timestamp())]),
    }


def detail_context(lead):
    members = get_db().execute('SELECT u.id,u.name,m.role FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.workspace_id=? ORDER BY u.name,u.id', (g.workspace['id'],)).fetchall()
    values = dict(lead)
    values['assigned_user_id'] = lead['assigned_user_id'] or ''
    values['workspace_timezone'] = g.workspace['timezone']
    values['followup_due'] = datetime.fromtimestamp(lead['followup_due'], ZoneInfo(g.workspace['timezone'])).strftime('%Y-%m-%dT%H:%M') if lead['followup_due'] is not None else ''
    return {'team':members, 'handoff_values':values, 'handoff_errors':{}, 'handoff_conflict':False,
            'followup_pending':lead['followup_due'] is not None and lead['followup_completed_at'] is None,
            'followup_overdue':lead['followup_due'] is not None and lead['followup_completed_at'] is None and lead['status'] != 'Closed' and lead['followup_due'] < utc_now().timestamp()}


def add_event(db, lead_id, description):
    db.execute('INSERT INTO lead_events(lead_id,workspace_id,actor,description,created) VALUES(?,?,?,?,?)',
               (lead_id, g.workspace['id'], g.user['name'], description, int(utc_now().timestamp())))


@bp.post('/leads/<lead_id>/follow-up')
@require_workspace
def save(lead_id):
    from .leads import render_detail
    db = get_db()
    errors, code = {}, 422
    with db:
        # Membership checks and the conditional lead write share one write lock.
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?', (g.workspace['id'],g.user['id'])).fetchone():
            abort(404)
        lead = db.execute('SELECT * FROM leads WHERE id=? AND workspace_id=?', (lead_id, g.workspace['id'])).fetchone()
        if not lead:
            abort(404)
        try:
            version = int(request.form.get('version', ''))
        except ValueError:
            version = -1
        if not 1 <= version <= 2_147_483_647:
            errors['form'] = 'This lead version is not valid. Reload before saving.'
        elif version != lead['version']:
            errors['form'] = 'Someone updated this lead. Reload the latest version before saving again.'
            code = 409
        operation = request.form.get('operation')
        if operation not in {'save', 'complete'}:
            errors['form'] = 'Choose a valid follow-up action.'
        if not errors and operation == 'complete':
            outcome = request.form.get('followup_outcome', '').strip()
            if not outcome or len(outcome) > 1000:
                errors['followup_outcome'] = 'Describe the outcome in 1 to 1000 characters.'
            if lead['followup_due'] is None or lead['followup_completed_at'] is not None:
                errors['form'] = 'There is no pending follow-up to complete.'
            if not errors:
                now = int(utc_now().timestamp())
                db.execute('UPDATE leads SET followup_completed_at=?,followup_outcome=?,updated=?,version=version+1 WHERE id=? AND workspace_id=? AND version=?', (now,outcome,now,lead_id,g.workspace['id'],version))
                add_event(db, lead_id, f'Follow-up completed: {outcome}')
        elif not errors:
            assignee = request.form.get('assigned_user_id', '').strip()
            member = db.execute('SELECT u.name FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.workspace_id=? AND m.user_id=?', (g.workspace['id'], assignee)).fetchone() if assignee else None
            if assignee and not member:
                errors['assigned_user_id'] = 'Choose a current teammate from this workspace.'
            action = request.form.get('followup_action', '').strip()
            raw_due = request.form.get('followup_due', '').strip()
            due = None
            if len(action) > 240:
                errors['followup_action'] = 'Keep the next action within 240 characters.'
            if action and not raw_due:
                errors['followup_due'] = 'Choose when this action is due.'
            if raw_due and not action:
                errors['followup_action'] = 'Describe the next action.'
            zone = db.execute('SELECT timezone FROM workspaces WHERE id=?', (g.workspace['id'],)).fetchone()['timezone']
            if raw_due and request.form.get('workspace_timezone') != zone:
                errors['form'] = 'The workspace timezone changed. Reload before entering a due time.'
                code = 409
            elif raw_due:
                try:
                    if lead['followup_due'] is not None and raw_due == datetime.fromtimestamp(lead['followup_due'], ZoneInfo(zone)).strftime('%Y-%m-%dT%H:%M'):
                        # datetime-local cannot carry fold/offset. Preserve the
                        # stored instant when its displayed wall time is unchanged.
                        due = lead['followup_due']
                    else:
                        due = parse_due(raw_due, zone)
                except ValueError as error:
                    errors['followup_due'] = str(error)
            if not errors:
                changed_followup = action != lead['followup_action'] or due != lead['followup_due']
                # Saving unchanged completed work must not revive its reminder.
                completed = None if changed_followup else lead['followup_completed_at']
                outcome = '' if changed_followup else lead['followup_outcome']
                db.execute('UPDATE leads SET assigned_user_id=?,followup_action=?,followup_due=?,followup_completed_at=?,followup_outcome=?,updated=?,version=version+1 WHERE id=? AND workspace_id=? AND version=?',
                           (assignee or None,action,due,completed,outcome,int(utc_now().timestamp()),lead_id,g.workspace['id'],version))
                if (assignee or None) != lead['assigned_user_id']:
                    add_event(db, lead_id, f'Assigned to {member["name"]}' if member else 'Unassigned from teammate')
                if changed_followup:
                    add_event(db, lead_id, f'Follow-up scheduled: {action} · {format_due(due, zone)} ({zone})' if due is not None else 'Follow-up cleared')
        if errors:
            values = {**detail_context(lead)['handoff_values'], **request.form.to_dict()}
            return render_detail(lead, code=code, handoff_errors=errors, handoff_values=values, handoff_conflict=code==409)
    flash('Follow-up completed.' if operation == 'complete' else 'Assignment and follow-up saved.', 'success')
    return redirect(url_for('leads.detail', lead_id=lead_id), code=303)


@bp.post('/workspace/timezone')
@require_workspace
def set_timezone():
    owner_only()
    zone = request.form.get('timezone', '')
    if zone not in TIMEZONES:
        from .leads import inbox
        return inbox(timezone_errors={'timezone':'Choose a timezone from the list.'}), 422
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        from .business_settings import require_owner
        require_owner(db)
        current = db.execute('SELECT settings_version FROM workspaces WHERE id=?',(g.workspace['id'],)).fetchone()
        raw_version = request.form.get('settings_version')
        if raw_version is not None and raw_version != str(current['settings_version']):
            from .leads import inbox
            return inbox(timezone_errors={'timezone':'Business settings changed. Reload before changing the timezone.'}),409
        db.execute('UPDATE workspaces SET timezone=?,settings_version=settings_version+1 WHERE id=?', (zone, g.workspace['id']))
    flash('Workspace timezone saved. Existing deadlines keep their original instant.', 'success')
    return redirect(url_for('leads.inbox'), code=303)
