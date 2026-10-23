"""Owner-managed public business details and truthful setup progress."""
import json
import re
import time

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .db import get_db
from .followups import TIMEZONES
from .security import require_workspace
from .validation import SERVICES, email, text

bp = Blueprint('business_settings', __name__)


def service_choices(workspace):
    return json.loads(workspace['services_json']) if workspace['services_json'] is not None else list(SERVICES)


def service_areas(workspace):
    return json.loads(workspace['service_areas_json'])


def require_owner(db=None):
    role = g.workspace['role'] if db is None else (db.execute(
        'SELECT role FROM memberships WHERE workspace_id=? AND user_id=?',
        (g.workspace['id'],g.user['id'])).fetchone() or {'role':None})['role']
    if role != 'owner':
        abort(403,description='Only the workspace owner can manage business settings and setup.')


def setup_state(workspace):
    db = get_db()
    configured = bool(workspace['name'] and (workspace['contact_email'] or workspace['contact_phone'])
                      and workspace['services_json'] is not None and service_choices(workspace) and service_areas(workspace))
    received = bool(db.execute("SELECT 1 FROM leads l WHERE l.workspace_id=? AND (l.source IN ('website_walkthrough','customer_form','customer_portal') OR (l.source='service' AND EXISTS (SELECT 1 FROM lead_events e WHERE e.lead_id=l.id AND e.workspace_id=l.workspace_id AND e.actor='Customer inquiry form' AND e.description='Inquiry received'))) LIMIT 1",(workspace['id'],)).fetchone())
    members = db.execute('SELECT count(*) FROM memberships WHERE workspace_id=?',(workspace['id'],)).fetchone()[0]
    pending = db.execute('SELECT count(*) FROM invitations WHERE workspace_id=? AND used=0 AND expires>?',(workspace['id'],int(time.time()))).fetchone()[0]
    shared = workspace['form_shared_at'] is not None
    completed = sum((configured,shared,received))
    return {'configured':configured,'shared':shared,'received':received,'members':members,'pending':pending,
            'completed':completed,'complete':completed==3}


def settings_values(workspace):
    return {key:workspace[key] for key in ('name','contact_email','contact_phone','timezone','settings_version')} | {
        'services':'\n'.join(service_choices(workspace)), 'service_areas':'\n'.join(service_areas(workspace))}


def line_list(form,key,maximum,errors,label):
    raw = form.get(key,'').strip()
    # Check controls before splitlines so vertical tabs cannot silently become entries.
    if any(ord(ch)<32 and ch not in '\r\n' for ch in raw) or '\x7f' in raw:
        errors[key] = f'Use plain text for {label}.'
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not 1<=len(lines)<=20 or any(len(line)>maximum for line in lines):
        errors[key] = f'Enter 1 to 20 {label}, one per line, up to {maximum} characters each.'
    elif len({line.casefold() for line in lines})!=len(lines):
        errors[key] = f'List each {"service" if key=="services" else "service area"} once.'
    return lines


@bp.route('/settings',methods=['GET','POST'])
@require_workspace
def settings():
    require_owner()
    values,errors,code,stale = settings_values(g.workspace),{},200,False
    if request.method=='POST':
        values.update(request.form.to_dict())
        for key,maximum in (('name',100),('contact_email',254),('contact_phone',40)):
            values[key] = text(request.form,key,maximum,errors,required=key=='name',label='business name' if key=='name' else key.replace('_',' '))
            if any(ord(ch)<32 or ord(ch)==127 for ch in values[key]):
                errors[key] = 'Use a single line of plain text.'
        values['contact_email'] = values['contact_email'].lower()
        if values['contact_email'] and not email(values['contact_email']):
            errors['contact_email'] = 'Enter a valid public email address.'
        if values['contact_phone']:
            phone = values['contact_phone']
            number,*extension = re.split('[xX]',phone)
            if (not re.fullmatch(r'\+?[0-9() .-]+(?:[xX][0-9 ]+)?',phone)
                    or not 7<=len(re.sub('[^0-9]','',number))<=15
                    or (extension and not 1<=len(re.sub('[^0-9]','',extension[0]))<=8)):
                errors['contact_phone'] = 'Use 7 to 15 number digits, with an optional extension of up to 8 digits.'
        if not values['contact_email'] and not values['contact_phone']:
            errors['contact_email'] = 'Add a public email address or phone number so customers can contact the business.'
        services = line_list(request.form,'services',60,errors,'services')
        areas = line_list(request.form,'service_areas',100,errors,'service areas')
        if values.get('timezone') not in TIMEZONES:
            errors['timezone'] = 'Choose a timezone from the list.'
        try: version = int(request.form.get('settings_version',''))
        except ValueError: version = -1
        if not 1<=version<=2_147_483_647:
            errors['form'] = 'This settings version is not valid. Reload before saving.'
        db = get_db()
        with db:
            db.execute('BEGIN IMMEDIATE')
            require_owner(db)
            current = db.execute('SELECT settings_version FROM workspaces WHERE id=?',(g.workspace['id'],)).fetchone()
            if not errors and version!=current['settings_version']:
                errors['form'] = 'Business settings changed while you were editing. Reload the latest version before saving.'
                code,stale = 409,True
            if not errors:
                db.execute('UPDATE workspaces SET name=?,contact_email=?,contact_phone=?,services_json=?,service_areas_json=?,timezone=?,settings_version=settings_version+1 WHERE id=? AND settings_version=?',
                    (values['name'],values['contact_email'],values['contact_phone'],json.dumps(services,ensure_ascii=False),json.dumps(areas,ensure_ascii=False),values['timezone'],g.workspace['id'],version))
        if not errors:
            flash('Business settings saved. The customer form now uses these details; existing leads and appointment instants are unchanged.','success')
            return redirect(url_for('business_settings.settings'),code=303)
        code = code if code==409 else 422
    return render_template('business_settings.html',title='Business settings',active='settings',values=values,errors=errors,stale=stale,timezones=TIMEZONES),code


@bp.route('/setup',methods=['GET','POST'])
@require_workspace
def setup():
    require_owner()
    errors = {}
    if request.method=='POST':
        operation = request.form.get('operation','')
        db = get_db()
        with db:
            db.execute('BEGIN IMMEDIATE')
            require_owner(db)
            if operation not in {'shared','unshared'}:
                errors['form'] = 'Choose a valid sharing action.'
            else:
                if operation=='shared':
                    db.execute('UPDATE workspaces SET form_shared_at=COALESCE(form_shared_at,?) WHERE id=?',(int(time.time()),g.workspace['id']))
                else:
                    db.execute('UPDATE workspaces SET form_shared_at=NULL WHERE id=?',(g.workspace['id'],))
        if not errors:
            flash('Your sharing acknowledgement was saved. This does not send the link to anyone.','success')
            return redirect(url_for('business_settings.setup'),code=303)
    return render_template('setup.html',title='Business setup',active='setup',setup=setup_state(g.workspace),errors=errors),422 if errors else 200
