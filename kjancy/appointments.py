"""Atomic, tenant-scoped appointment scheduling and conflict acknowledgement."""
from datetime import datetime
import uuid
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from itsdangerous import BadSignature, URLSafeTimedSerializer

from .db import get_db
from .followups import add_event, format_due, parse_due, utc_now
from .security import require_workspace

bp = Blueprint('appointments', __name__)


def current_appointment(db, lead_id):
    return db.execute("SELECT a.*,u.name AS assignee_name FROM appointments a LEFT JOIN users u ON u.id=a.assigned_user_id WHERE a.workspace_id=? AND a.lead_id=? AND a.state='scheduled'", (g.workspace['id'],lead_id)).fetchone()


def local_input(instant, zone):
    return datetime.fromtimestamp(instant,ZoneInfo(zone)).strftime('%Y-%m-%dT%H:%M')


def lead_context(lead):
    db = get_db()
    current = current_appointment(db,lead['id'])
    previous = db.execute("SELECT * FROM appointments WHERE workspace_id=? AND lead_id=? AND state='cancelled' ORDER BY updated DESC,id DESC LIMIT 1",(g.workspace['id'],lead['id'])).fetchone()
    return {'appointment':current,'previous_appointment':previous,
            'appointment_date':local_input(current['start_at'],g.workspace['timezone'])[:10] if current else ''}


def render_editor(lead, current, values=None, errors=None, conflicts=(), token='', code=200, stale=False):
    defaults = {'version':lead['version'],'appointment_id':current['id'] if current else '',
                'assigned_user_id':current['assigned_user_id'] if current else (lead['assigned_user_id'] or ''),
                'start':local_input(current['start_at'],g.workspace['timezone']) if current else '',
                'duration_minutes':str((current['end_at']-current['start_at'])//60) if current else '60',
                'workspace_timezone':g.workspace['timezone'],'cancellation_reason':''}
    members = get_db().execute('SELECT u.id,u.name FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.workspace_id=? ORDER BY u.name,u.id',(g.workspace['id'],)).fetchall()
    return render_template('appointment_edit.html',title='Reschedule appointment' if current else 'Schedule appointment',lead=lead,
        appointment=current,values={**defaults,**(values or {})},errors=errors or {},team=members,
        conflicts=conflicts,overlap_token=token,stale=stale,active='calendar'),code


def cancel_record(db, appointment, reason):
    db.execute("UPDATE appointments SET state='cancelled',cancellation_reason=?,updated=? WHERE id=? AND workspace_id=? AND state='scheduled'",(reason,int(utc_now().timestamp()),appointment['id'],g.workspace['id']))
    add_event(db,appointment['lead_id'],f'Appointment cancelled: {reason}')


def release_member(db, user_id, already_versioned):
    affected = db.execute("SELECT id,lead_id FROM appointments WHERE workspace_id=? AND assigned_user_id=? AND state='scheduled'",(g.workspace['id'],user_id)).fetchall()
    now = int(utc_now().timestamp())
    db.execute("UPDATE appointments SET assigned_user_id=NULL,updated=? WHERE workspace_id=? AND assigned_user_id=? AND state='scheduled'",(now,g.workspace['id'],user_id))
    for item in affected:
        if item['lead_id'] not in already_versioned:
            db.execute('UPDATE leads SET version=version+1,updated=? WHERE id=? AND workspace_id=?',(now,item['lead_id'],g.workspace['id']))
        add_event(db,item['lead_id'],'Appointment unassigned because teammate access was removed')


def conflict_payload(lead, assignee, start, end, conflicts):
    return {'workspace':g.workspace['id'],'lead':lead['id'],'version':lead['version'],'assignee':assignee,'start':start,'end':end,
            'conflicts':[[row['id'],row['start_at'],row['end_at'],row['assigned_user_id'],row['updated']] for row in conflicts]}


@bp.route('/leads/<lead_id>/appointment',methods=['GET','POST'])
@require_workspace
def edit(lead_id):
    db = get_db()
    if request.method == 'GET':
        lead = db.execute('SELECT * FROM leads WHERE id=? AND workspace_id=?',(lead_id,g.workspace['id'])).fetchone()
        if not lead: abort(404)
        return render_editor(lead,current_appointment(db,lead_id))
    values = request.form.to_dict()
    errors, conflicts, token, code, stale = {}, [], '', 422, False
    with db:
        db.execute('BEGIN IMMEDIATE')
        if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(g.workspace['id'],g.user['id'])).fetchone():
            abort(404)
        lead = db.execute('SELECT * FROM leads WHERE id=? AND workspace_id=?',(lead_id,g.workspace['id'])).fetchone()
        if not lead: abort(404)
        current = current_appointment(db,lead_id)
        try: version = int(values.get('version',''))
        except ValueError: version = -1
        if not 1 <= version <= 2_147_483_647:
            errors['form'] = 'This lead version is not valid. Reload before saving.'
        elif version != lead['version'] or values.get('appointment_id','') != (current['id'] if current else ''):
            errors['form'] = 'This lead or appointment changed. Reload the latest version before saving.'
            code, stale = 409, True
        operation = values.get('operation')
        if operation not in {'save','cancel'}:
            errors['form'] = 'Choose a valid appointment action.'
        if not errors and operation == 'cancel':
            reason = values.get('cancellation_reason','').strip()
            if not current:
                errors['form'] = 'There is no active appointment to cancel.'
            if not reason or len(reason)>500:
                errors['cancellation_reason'] = 'Give a cancellation reason in 1 to 500 characters.'
            if not errors:
                cancel_record(db,current,reason)
                status = 'Contacted' if lead['status']=='Appointment booked' else lead['status']
                db.execute('UPDATE leads SET status=?,updated=?,version=version+1 WHERE id=? AND workspace_id=? AND version=?',(status,int(utc_now().timestamp()),lead_id,g.workspace['id'],version))
        elif not errors:
            if lead['status']=='Closed':
                errors['form'] = 'Reopen this lead before scheduling an appointment.'
            assignee = values.get('assigned_user_id','')
            member = db.execute('SELECT u.name FROM users u JOIN memberships m ON m.user_id=u.id WHERE m.workspace_id=? AND m.user_id=?',(g.workspace['id'],assignee)).fetchone()
            if not member:
                errors['assigned_user_id'] = 'Choose a current teammate from this workspace.'
            try:
                duration = int(values.get('duration_minutes',''))
                if not 15<=duration<=480 or duration%15: raise ValueError()
            except ValueError:
                errors['duration_minutes'] = 'Choose 15 to 480 minutes, in 15-minute increments.'
            zone = db.execute('SELECT timezone FROM workspaces WHERE id=?',(g.workspace['id'],)).fetchone()['timezone']
            start = None
            if values.get('workspace_timezone') != zone:
                errors['form'] = 'The workspace timezone changed. Reload before entering an appointment time.'
                code, stale = 409, True
            else:
                try:
                    raw = values.get('start','')
                    start = current['start_at'] if current and raw==local_input(current['start_at'],zone) else parse_due(raw,zone)
                except ValueError as error:
                    errors['start'] = str(error)
            if not errors:
                end = start+duration*60
                conflicts = db.execute("SELECT a.*,l.customer_name FROM appointments a JOIN leads l ON l.id=a.lead_id AND l.workspace_id=a.workspace_id WHERE a.workspace_id=? AND a.assigned_user_id=? AND a.state='scheduled' AND a.id!=? AND a.start_at<? AND a.end_at>? ORDER BY a.start_at,a.id",(g.workspace['id'],assignee,current['id'] if current else '',end,start)).fetchall()
                payload = conflict_payload(lead,assignee,start,end,conflicts)
                signer = URLSafeTimedSerializer(current_app.secret_key,salt='appointment-overlap-v1')
                accepted = False
                if conflicts and values.get('confirm_overlap')=='yes':
                    try: accepted = signer.loads(values.get('overlap_token',''),max_age=600)==payload
                    except BadSignature: pass
                if conflicts and not accepted:
                    errors['form'] = 'This teammate has overlapping appointments. Review them before scheduling anyway.'
                    token, code = signer.dumps(payload), 409
                else:
                    now = int(utc_now().timestamp())
                    if current:
                        db.execute('UPDATE appointments SET assigned_user_id=?,start_at=?,end_at=?,updated=? WHERE id=? AND workspace_id=?',(assignee,start,end,now,current['id'],g.workspace['id']))
                    else:
                        db.execute("INSERT INTO appointments(id,workspace_id,lead_id,assigned_user_id,start_at,end_at,state,created,updated) VALUES(?,?,?,?,?,?,'scheduled',?,?)",(uuid.uuid4().hex,g.workspace['id'],lead_id,assignee,start,end,now,now))
                    db.execute("UPDATE leads SET status='Appointment booked',updated=?,version=version+1 WHERE id=? AND workspace_id=? AND version=?",(now,lead_id,g.workspace['id'],version))
                    description = f'Appointment {"rescheduled" if current else "scheduled"}: {format_due(start,zone)} ({zone}), {duration} minutes, {member["name"]}'
                    if conflicts: description += ' · Overlap explicitly acknowledged'
                    add_event(db,lead_id,description)
        if errors:
            return render_editor(lead,current,values,errors,conflicts,token,code,stale)
    flash('Appointment cancelled. The calendar and lead status were updated.' if operation=='cancel' else 'Appointment saved in your workspace calendar. Contact the customer to confirm.', 'success')
    return redirect(url_for('leads.detail',lead_id=lead_id),code=303)
