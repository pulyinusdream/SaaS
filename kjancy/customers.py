"""Customer account onboarding, owned service requests and safe read projections."""
from functools import wraps
import re
import secrets
import sqlite3
import time
import uuid

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from itsdangerous import BadData, URLSafeTimedSerializer
from werkzeug.security import generate_password_hash

from . import business_settings, customer_messages
from .account import issue_link
from .account_settings import active_account
from .db import get_db
from .leads import create_lead
from .security import home_endpoint, portal_mismatch, rate_limit, require_login, start_session
from .validation import STATUSES, email, lead_values, text

bp = Blueprint('customers',__name__)
PAGE_SIZE = 25
SAFE_FIELDS = 'l.id,l.workspace_id,l.customer_user_id,l.customer_name,l.email,l.phone,l.service,l.location,l.message,l.status,l.created,l.updated'


def require_customer(view):
    @wraps(view)
    @require_login
    def wrapped(*args,**kwargs):
        if g.user['account_kind']!='customer' or g.customer is None:
            abort(403,description='This area is for customer accounts. Use your business workspace for administration.')
        return view(*args,**kwargs)
    return wrapped


def fresh_customer(db):
    user = active_account(db)
    if user['account_kind']!='customer':
        abort(403,description='This account no longer has customer access.')
    profile = db.execute('SELECT * FROM customer_accounts WHERE user_id=?',(user['id'],)).fetchone()
    if not profile:
        abort(403,description='Customer account details are unavailable. Contact the business.')
    business = db.execute('SELECT * FROM workspaces WHERE id=?',(profile['workspace_id'],)).fetchone()
    if not business: abort(404)
    return profile,business


def submission_signer():
    return URLSafeTimedSerializer(current_app.secret_key,salt='customer-request-v1')


@bp.route('/customer/signup/<public_id>',methods=['GET','POST'])
def signup(public_id):
    db = get_db()
    business = db.execute('SELECT name,id,public_id FROM workspaces WHERE public_id=?',(public_id,)).fetchone()
    if not business: abort(404)
    if g.user:
        if g.user['account_kind']!='customer': return portal_mismatch('customer',business)
        return redirect(url_for(home_endpoint(g.user)),code=303)
    errors,values = {},{}
    if request.method=='POST':
        rate_limit('customer-signup',10)
        values['name'] = text(request.form,'name',100,errors,required=True,label='your name')
        values['email'] = request.form.get('email','').strip().lower()
        if any(ord(ch)<32 or ord(ch)==127 for ch in values['name']): errors['name'] = 'Use a single line for your name.'
        if not email(values['email']): errors['email'] = 'Enter a valid email address.'
        password = request.form.get('password','')
        if not 12<=len(password)<=128: errors['password'] = 'Use a password with 12 to 128 characters.'
        if not errors:
            uid,now = uuid.uuid4().hex,int(time.time())
            hashed = generate_password_hash(password,method='scrypt')
            try:
                with db:
                    db.execute('INSERT INTO users(id,name,email,password_hash,created,account_kind) VALUES(?,?,?,?,?,\'customer\')',(uid,values['name'],values['email'],hashed,now))
                    db.execute('INSERT INTO customer_accounts(user_id,workspace_id) VALUES(?,?)',(uid,business['id']))
            except sqlite3.IntegrityError:
                errors['email'] = 'An account already uses this email. Sign in instead.'
            else:
                if not start_session(uid,hashed): return redirect('/customer/login',code=303)
                user = db.execute('SELECT * FROM users WHERE id=?',(uid,)).fetchone()
                if not issue_link(user,'verify'): flash('Account saved. Its verification message could not be prepared; try again from Account settings.','error')
                if current_app.config['REQUIRE_EMAIL_VERIFICATION']: return redirect(url_for('account.email_status'),code=303)
                flash('Your customer account is ready. Save your contact details to get started.','success')
                return redirect(url_for('customers.get_started'),code=303)
    return render_template('customer_signup.html',title='Create customer account',business=business,values=values,errors=errors,public_page=True),422 if errors else 200


@bp.get('/customer')
@require_customer
def home():
    db = get_db()
    with db:
        db.execute('BEGIN')
        profile,business = fresh_customer(db)
        status = request.args.get('status','')
        if status and status not in STATUSES: abort(400,description='Choose one of the available request statuses.')
        counts = dict.fromkeys(STATUSES,0)
        scope = (g.user['id'],business['id'])
        for row in db.execute('SELECT status,count(*) AS n FROM leads WHERE customer_user_id=? AND workspace_id=? GROUP BY status',scope): counts[row['status']] = row['n']
        total = counts[status] if status else sum(counts.values())
        pages = max(1,(total+PAGE_SIZE-1)//PAGE_SIZE)
        try: page = max(1,min(int(request.args.get('page','1')),pages))
        except ValueError: page = 1
        where,args = 'l.customer_user_id=? AND l.workspace_id=?',list(scope)
        if status: where+=' AND l.status=?'; args.append(status)
        rows = db.execute(f'SELECT {SAFE_FIELDS},{customer_messages.unread_sql("l","customer")} AS unread_message_count FROM leads l WHERE {where} ORDER BY l.created DESC,l.id DESC LIMIT ? OFFSET ?',[g.user['id'],*args,PAGE_SIZE,(page-1)*PAGE_SIZE]).fetchall()
        return render_template('customer_home.html',title='My requests',active='customer_home',business=business,profile=profile,requests=rows,counts=counts,total=total,all_total=sum(counts.values()),selected_status=status,page=page,pages=pages)


@bp.route('/customer/get-started',methods=['GET','POST'])
@require_customer
def get_started():
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE' if request.method=='POST' else 'BEGIN')
        profile,business = fresh_customer(db)
        values,errors,stale,code = dict(profile),{},False,200
        if request.method=='POST':
            values['phone'] = text(request.form,'phone',40,errors,label='phone number')
            values['location'] = text(request.form,'location',200,errors,required=True,label='service location')
            if values['phone'] and not re.fullmatch(r'[+()0-9 .xX-]{7,40}',values['phone']): errors['phone'] = 'Enter a valid phone number.'
            if any(ord(ch)<32 or ord(ch)==127 for ch in values['location']): errors['location'] = 'Use a single line for the service location.'
            version = request.form.get('version','')
            if not re.fullmatch(r'[1-9]\d{0,9}',version): errors['form'] = 'Reload this form before saving your contact details.'
            elif int(version)!=profile['version']:
                errors['form'] = 'Your contact details changed in another tab. Reload before saving.'
                stale,code = True,409
            if not errors:
                db.execute('UPDATE customer_accounts SET phone=?,location=?,version=version+1,completed_at=? WHERE user_id=?',(values['phone'],values['location'],int(time.time()),g.user['id']))
                flash('Your contact defaults were saved. You can use a different address on each request.','success')
                return redirect(url_for('customers.get_started'),code=303)
            code = 409 if stale else 422
        received = bool(db.execute('SELECT 1 FROM leads WHERE customer_user_id=? AND workspace_id=? LIMIT 1',(g.user['id'],business['id'])).fetchone())
        return render_template('customer_setup.html',title='Contact details',active='customer_setup',business=business,profile=profile,values=values,errors=errors,stale=stale,received=received),code


@bp.route('/customer/form',methods=['GET','POST'])
@require_customer
def form():
    if request.method=='POST': rate_limit('customer-request',20,3600)
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE' if request.method=='POST' else 'BEGIN')
        profile,business = fresh_customer(db)
        values = {'phone':profile['phone'],'location':profile['location'],'customer_name':g.user['name'],'email':g.user['email']}
        errors = {}
        if request.method=='POST':
            token = request.form.get('request_token','')
            try:
                signed = submission_signer().loads(token,max_age=3600)
                if (not isinstance(signed,dict) or signed.get('user')!=g.user['id'] or signed.get('business')!=business['id']
                        or not isinstance(signed.get('nonce'),str) or not re.fullmatch(r'[a-f0-9]{32}',signed['nonce'])): raise BadData('Wrong customer scope')
            except BadData: abort(400,description='This request form expired or changed. Reopen Customer form and try again.')
            key = 'customer:'+signed['nonce']
            existing = db.execute('SELECT id FROM leads WHERE submission_key=? AND customer_user_id=? AND workspace_id=?',(key,g.user['id'],business['id'])).fetchone()
            if existing: return redirect(url_for('customers.detail',lead_id=existing['id']),code=303)
            if request.form.get('website_url',''): abort(400,description='This request could not be verified.')
            submitted = request.form.to_dict() | {'customer_name':g.user['name'],'email':g.user['email']}
            values,errors = lead_values(submitted,business_settings.service_choices(business))
            if not errors:
                values.update(source='customer_portal',customer_user_id=g.user['id'],submission_key=key)
                lead_id = create_lead(business,values,'Customer portal')
                flash('Your service request was sent to the business. An appointment has not been booked yet.','success')
                return redirect(url_for('customers.detail',lead_id=lead_id),code=303)
        else:
            token = submission_signer().dumps({'user':g.user['id'],'business':business['id'],'nonce':uuid.uuid4().hex})
        return render_template('customer_form.html',title='New request',active='customer_form',business=business,values=values,errors=errors,request_token=token,services=business_settings.service_choices(business),service_areas=business_settings.service_areas(business)),422 if errors else 200


@bp.get('/customer/requests/<lead_id>')
@require_customer
def detail(lead_id):
    db = get_db()
    with db:
        db.execute('BEGIN')
        profile,business = fresh_customer(db)
        lead = db.execute(f'SELECT {SAFE_FIELDS} FROM leads l WHERE l.id=? AND l.customer_user_id=? AND l.workspace_id=?',(lead_id,g.user['id'],business['id'])).fetchone()
        if not lead: abort(404)
        return render_request_detail(db,lead,business)


def render_request_detail(db,lead,business,*,message_errors=None,message_body='',message_token=None,code=200):
    appointment = db.execute("SELECT state,start_at,end_at FROM appointments WHERE lead_id=? AND workspace_id=? ORDER BY (state='scheduled') DESC,updated DESC,id DESC LIMIT 1",(lead['id'],business['id'])).fetchone()
    return render_template('customer_detail.html',title='Your service request',active='customer_home',business=business,lead=lead,appointment=appointment,
        message_errors=message_errors or {},message_body=message_body,
        message_token=message_token or customer_messages.new_token(g.user['id'],business['id'],lead['id']),
        **customer_messages.history_context(lead,'customers.detail',g.user['id'])),code


@bp.post('/customer/requests/<lead_id>/messages')
@require_customer
def send_message(lead_id):
    rate_limit('customer-followup:'+g.user['id'],20,3600)
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        profile,business = fresh_customer(db)
        lead = db.execute(f'SELECT {SAFE_FIELDS} FROM leads l WHERE l.id=? AND l.customer_user_id=? AND l.workspace_id=?',
                          (lead_id,g.user['id'],business['id'])).fetchone()
        if not lead: abort(404)
        token = request.form.get('message_token','')
        try:
            signed = customer_messages.signer().loads(token,max_age=3600)
            if (not isinstance(signed,dict) or signed.get('user')!=g.user['id'] or signed.get('business')!=business['id']
                    or signed.get('lead')!=lead_id or not isinstance(signed.get('nonce'),str)
                    or not re.fullmatch(r'[a-f0-9]{32}',signed['nonce'])): raise BadData('Wrong request scope')
        except BadData:
            abort(400,description='This follow-up form expired or changed. Reopen your request and try again.')
        key = 'customer-followup:'+signed['nonce']
        destination = url_for('customers.detail',lead_id=lead_id,_anchor='follow-up-messages')
        if db.execute('SELECT 1 FROM customer_request_messages WHERE submission_key=? AND lead_id=? AND workspace_id=? AND customer_user_id=?',
                      (key,lead_id,business['id'],g.user['id'])).fetchone():
            return redirect(destination,code=303)
        errors = {}
        body = text(request.form,'followup_message',2000,errors,required=True,label='a follow-up message')
        if errors:
            return render_request_detail(db,lead,business,message_errors=errors,message_body=body,message_token=token,code=422)
        now = int(time.time())
        db.execute('INSERT INTO customer_request_messages(lead_id,workspace_id,customer_user_id,sender_name,body,submission_key,created) VALUES(?,?,?,?,?,?,?)',
                   (lead_id,business['id'],g.user['id'],g.user['name'],body,key,now))
        db.execute('INSERT INTO lead_events(lead_id,workspace_id,actor,description,created) VALUES(?,?,?,?,?)',
                   (lead_id,business['id'],g.user['name'],'Customer follow-up message received',now))
        flash('Your follow-up message was sent to '+business['name']+'.','success')
        return redirect(destination,code=303)


@bp.post('/customer/requests/<lead_id>/messages/read')
@require_customer
def read_messages(lead_id):
    rate_limit('customer-message-read:'+g.user['id'],120,3600)
    db = get_db()
    with db:
        db.execute('BEGIN IMMEDIATE')
        profile,business = fresh_customer(db)
        lead = db.execute('SELECT * FROM leads WHERE id=? AND workspace_id=? AND customer_user_id=?',
                          (lead_id,business['id'],g.user['id'])).fetchone()
        if not lead: abort(404)
        page = customer_messages.mark_displayed_read(db,lead)
        return redirect(url_for('customers.detail',lead_id=lead_id,messages_page=page,_anchor='follow-up-messages'),code=303)
