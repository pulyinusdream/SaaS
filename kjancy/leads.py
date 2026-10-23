import time
import uuid

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for

from .db import get_db
from .account_settings import active_account
from . import appointments, business_settings, followups, customer_messages
from .security import rate_limit, require_workspace
from .validation import SERVICES, STATUSES, lead_values, text

bp = Blueprint('leads', __name__)


def create_lead(workspace, values, actor):
    uid, now = uuid.uuid4().hex, int(time.time())
    db = get_db()
    with db:
        db.execute('INSERT INTO leads(id,workspace_id,customer_name,email,phone,service,location,message,created,updated,source,business_name,support_plan,submission_key,customer_user_id) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                   (uid, workspace['id'], values['customer_name'], values['email'], values['phone'], values['service'], values['location'], values['message'], now, now, values.get('source', 'service'), values.get('business_name', ''), values.get('support_plan', ''), values.get('submission_key'),values.get('customer_user_id')))
        db.execute('INSERT INTO lead_events(lead_id,workspace_id,actor,description,created) VALUES(?,?,?,?,?)', (uid, workspace['id'], actor, 'Inquiry received', now))
    return uid


@bp.get('/inbox')
@require_workspace
def inbox(timezone_errors=None):
    status = request.args.get('status', '')
    if status and status not in STATUSES:
        abort(400, description='Choose one of the available lead statuses.')
    query = request.args.get('q', '').strip()[:100]
    try:
        page = max(1, min(int(request.args.get('page', '1')), 100000))
    except ValueError:
        page = 1
    db = get_db()
    views = followups.queue_views()
    selected_view = request.args.get('view', 'all')
    if selected_view not in views:
        abort(400, description='Choose one of the available work views.')
    _, view_clause, view_args = views[selected_view]
    where, args = ['l.workspace_id=?', '(' + view_clause + ')'], [g.workspace['id'], *view_args]
    if status:
        where.append('l.status=?')
        args.append(status)
    if query:
        safe = query.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        where.append("(l.customer_name LIKE ? ESCAPE '\\' OR l.email LIKE ? ESCAPE '\\' OR l.phone LIKE ? ESCAPE '\\' OR l.service LIKE ? ESCAPE '\\' OR l.location LIKE ? ESCAPE '\\' OR l.business_name LIKE ? ESCAPE '\\' OR l.support_plan LIKE ? ESCAPE '\\')")
        args += [f'%{safe}%'] * 7
    clause = ' AND '.join(where)
    joined = 'leads l ' + followups.ASSIGNEE_JOIN
    total = db.execute(f'SELECT count(*) AS n FROM {joined} WHERE {clause}', args).fetchone()['n']
    page = min(page, max(1, (total + 19) // 20))
    order = 'l.followup_due ASC,l.id DESC' if selected_view in {'today','overdue'} else 'l.created DESC,l.id DESC'
    items = db.execute(f'SELECT l.*,au.name AS assignee_name,(SELECT count(*) FROM customer_request_messages cm WHERE cm.lead_id=l.id AND cm.workspace_id=l.workspace_id AND cm.sender_kind=\'customer\') AS customer_message_count,{customer_messages.unread_sql("l","staff")} AS unread_message_count FROM {joined} WHERE {clause} ORDER BY {order} LIMIT 20 OFFSET ?', [g.user['id'],*args, (page - 1) * 20]).fetchall()
    counts = {s: 0 for s in STATUSES}
    counts.update({row['status']: row['n'] for row in db.execute(f'SELECT l.status,count(*) AS n FROM {joined} WHERE l.workspace_id=? AND ({view_clause}) GROUP BY l.status', (g.workspace['id'], *view_args))})
    work_views = {key:{'label':label, 'count':db.execute(f'SELECT count(*) FROM {joined} WHERE l.workspace_id=? AND ({predicate})', (g.workspace['id'], *parameters)).fetchone()[0]} for key,(label,predicate,parameters) in views.items()}
    return render_template('inbox.html', title='Customer requests', leads=items, counts=counts, total=total, page=page, pages=max(1, (total + 19) // 20), query=query, selected_status=status, selected_view=selected_view, work_views=work_views, active='inbox', timezones=followups.TIMEZONES, timezone_errors=timezone_errors or {}, now_epoch=int(followups.utc_now().timestamp()), setup=business_settings.setup_state(g.workspace) if g.workspace['role']=='owner' else None)


@bp.route('/leads/new', methods=['GET', 'POST'])
@require_workspace
def new():
    values, errors = {}, {}
    workspace = g.workspace
    if request.method == 'POST':
        rate_limit('manual-lead', 100)
        db = get_db()
        with db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(g.workspace['id'],g.user['id'])).fetchone():
                abort(404)
            workspace = db.execute('SELECT * FROM workspaces WHERE id=?',(g.workspace['id'],)).fetchone()
            values, errors = lead_values(request.form,business_settings.service_choices(workspace))
            if not errors:
                values['source'] = 'manual'
                uid = create_lead(workspace, values, g.user['name'])
        if not errors:
            flash('Lead added to this workspace.', 'success')
            return redirect(url_for('leads.detail', lead_id=uid), code=303)
    return render_template('lead_new.html', title='Add a lead', values=values, errors=errors, active='inbox',services=business_settings.service_choices(workspace)), 422 if errors else 200


@bp.route('/leads/<lead_id>', methods=['GET', 'POST'])
@require_workspace
def detail(lead_id):
    db = get_db()
    lead = db.execute('SELECT * FROM leads WHERE id=? AND workspace_id=?', (lead_id, g.workspace['id'])).fetchone()
    if not lead:
        abort(404)
    errors = {}
    values = dict(lead)
    code = 200
    if request.method == 'POST':
        status = request.form.get('status', '')
        notes = text(request.form, 'internal_notes', 4000, errors)
        if status not in STATUSES:
            errors['status'] = 'Choose a valid lead status.'
        try:
            version = int(request.form.get('version', ''))
        except ValueError:
            version = -1
        if not 1 <= version <= 2_147_483_647:
            errors['form'] = 'This lead version is not valid. Reload the page before saving.'
        if not errors:
            now = int(time.time())
            with db:
                db.execute('BEGIN IMMEDIATE')
                if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?', (g.workspace['id'],g.user['id'])).fetchone():
                    abort(404)
                current = db.execute('SELECT * FROM leads WHERE id=? AND workspace_id=?',(lead_id,g.workspace['id'])).fetchone()
                appointment = appointments.current_appointment(db,lead_id)
                if not current or current['version'] != version:
                    errors['form'] = 'Someone updated this lead while you were editing. Reload the latest version before saving again.'
                    code = 409
                elif appointment and status in {'New','Contacted'}:
                    errors['status'] = 'Cancel the scheduled appointment before moving this lead back to New or Contacted.'
                    code = 422
                else:
                    db.execute('UPDATE leads SET status=?,internal_notes=?,version=version+1,updated=? WHERE id=? AND workspace_id=? AND version=?',
                               (status,notes,now,lead_id,g.workspace['id'],version))
                    if appointment and status=='Closed':
                        appointments.cancel_record(db,appointment,'Lead closed')
                    description = f'Status changed from {current["status"]} to {status}' if current['status'] != status else 'Internal notes updated'
                    db.execute('INSERT INTO lead_events(lead_id,workspace_id,actor,description,created) VALUES(?,?,?,?,?)', (lead_id, g.workspace['id'], g.user['name'], description, now))
            if not errors:
                flash('Lead updated.', 'success')
                return redirect(url_for('leads.detail', lead_id=lead_id), code=303)
        else:
            code = 422
        values.update(status=status, internal_notes=notes)
    return render_detail(lead, values=values, errors=errors, code=code)


def render_detail(lead, values=None, errors=None, code=200, **overrides):
    events = get_db().execute('SELECT * FROM lead_events WHERE lead_id=? AND workspace_id=? ORDER BY created DESC,id DESC', (lead['id'], g.workspace['id'])).fetchall()
    eligible_customer = get_db().execute("SELECT 1 FROM customer_accounts c JOIN users u ON u.id=c.user_id WHERE c.user_id=? AND c.workspace_id=? AND u.account_kind='customer'",(lead['customer_user_id'],lead['workspace_id'])).fetchone()
    context = {**followups.detail_context(lead), **appointments.lead_context(lead), **customer_messages.history_context(lead,'leads.detail'),
               'can_reply':bool(eligible_customer),'reply_errors':{},'reply_body':'',
               'reply_token':customer_messages.new_token(g.user['id'],lead['workspace_id'],lead['id'],'staff') if eligible_customer else None, **overrides}
    return render_template('lead_detail.html', title=lead['customer_name'], lead=lead, values=values if values is not None else dict(lead), errors=errors or {}, events=events, conflict=code==409 and not overrides.get('handoff_conflict'), active='inbox', **context), code


def fresh_conversation_lead(db,lead_id):
    user = active_account(db)
    if user['account_kind']!='staff': abort(403)
    if not db.execute('SELECT 1 FROM memberships WHERE workspace_id=? AND user_id=?',(g.workspace['id'],user['id'])).fetchone(): abort(404)
    lead = db.execute("SELECT l.* FROM leads l JOIN customer_accounts c ON c.user_id=l.customer_user_id AND c.workspace_id=l.workspace_id JOIN users u ON u.id=c.user_id AND u.account_kind='customer' WHERE l.id=? AND l.workspace_id=?",
                      (lead_id,g.workspace['id'])).fetchone()
    if not lead: abort(404,description='This request does not have a customer portal account in this business. Use its contact details to reply.')
    return lead


@bp.post('/leads/<lead_id>/messages')
@require_workspace
def send_reply(lead_id):
    rate_limit('staff-reply:'+g.user['id'],60,3600)
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        lead = fresh_conversation_lead(db,lead_id)
        token = request.form.get('reply_token','')
        key = customer_messages.reply_key(token,lead)
        destination = url_for('leads.detail',lead_id=lead_id,_anchor='follow-up-messages')
        if db.execute("SELECT 1 FROM customer_request_messages WHERE submission_key=? AND lead_id=? AND workspace_id=? AND staff_user_id=? AND sender_kind='staff'",
                      (key,lead_id,lead['workspace_id'],g.user['id'])).fetchone(): return redirect(destination,code=303)
        errors = {}
        body = text(request.form,'reply_message',2000,errors,required=True,label='a reply')
        if errors: return render_detail(lead,code=422,reply_errors=errors,reply_body=body,reply_token=token)
        now = int(time.time())
        db.execute("INSERT INTO customer_request_messages(lead_id,workspace_id,customer_user_id,sender_name,sender_kind,staff_user_id,body,submission_key,created) VALUES(?,?,?,?,'staff',?,?,?,?)",
                   (lead_id,lead['workspace_id'],lead['customer_user_id'],g.user['name'],g.user['id'],body,key,now))
        db.execute('INSERT INTO lead_events(lead_id,workspace_id,actor,description,created) VALUES(?,?,?,?,?)',
                   (lead_id,lead['workspace_id'],g.user['name'],'Business reply sent to customer',now))
        flash('Your reply was sent to the customer portal. No email notification was sent.','success')
        return redirect(destination,code=303)


@bp.post('/leads/<lead_id>/messages/read')
@require_workspace
def read_messages(lead_id):
    rate_limit('staff-message-read:'+g.user['id'],120,3600)
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        lead = fresh_conversation_lead(db,lead_id)
        page = customer_messages.mark_displayed_read(db,lead)
        return redirect(url_for('leads.detail',lead_id=lead_id,messages_page=page,_anchor='follow-up-messages'),code=303)


@bp.route('/request/<public_id>', methods=['GET', 'POST'])
def public_request(public_id):
    workspace = get_db().execute('SELECT * FROM workspaces WHERE public_id=?', (public_id,)).fetchone()
    if not workspace:
        abort(404)
    if g.user:
        if request.method=='POST':
            abort(403,description='Signed-in accounts cannot submit the guest form. Customers use Customer form; staff record incoming inquiries in the Admin inbox.')
        if g.user['account_kind']=='customer':
            if not g.customer or g.customer['workspace_id']!=workspace['id']:
                abort(403,description='This business is not linked to your customer account. Return to your own requests.')
            return redirect(url_for('customers.form'),code=303)
        return render_template('inquiry.html',title='Customer form preview',business=workspace,values={},errors={},
                               services=business_settings.service_choices(workspace),service_areas=business_settings.service_areas(workspace),staff_preview=True)
    errors, values = {}, {}
    if request.method == 'POST':
        rate_limit(f'public-inquiry:{workspace["id"]}', 20, 3600)
        if request.form.get('website_url', ''):
            abort(400, description='This inquiry could not be verified.')
        db = get_db()
        with db:
            db.execute('BEGIN IMMEDIATE')
            workspace = db.execute('SELECT * FROM workspaces WHERE public_id=?',(public_id,)).fetchone()
            if not workspace: abort(404)
            values, errors = lead_values(request.form,business_settings.service_choices(workspace))
            if not errors:
                values['source'] = 'customer_form'
                create_lead(workspace, values, 'Customer inquiry form')
        if not errors:
            return redirect(url_for('leads.thank_you', public_id=public_id), code=303)
    return render_template('inquiry.html', title=f'Request service · {workspace["name"]}', business=workspace, values=values, errors=errors,services=business_settings.service_choices(workspace),service_areas=business_settings.service_areas(workspace)), 422 if errors else 200


@bp.get('/request/<public_id>/received')
def thank_you(public_id):
    workspace = get_db().execute('SELECT name FROM workspaces WHERE public_id=?', (public_id,)).fetchone()
    if not workspace:
        abort(404)
    return render_template('received.html', title='Inquiry received', business=workspace)
