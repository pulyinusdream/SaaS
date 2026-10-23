"""Explicit local sample provisioning, never automatic authentication or seeding."""
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit
import uuid

from werkzeug.security import generate_password_hash

from .backup import APP_ROOT
from .db import get_db


def provision_sample_customer(app,owner_email,credentials_path):
    origin = urlsplit(app.config['PUBLIC_BASE_URL'])
    if (app.config['MAIL_MODE']!='preview' or app.config.get('ENFORCE_HTTPS') or origin.scheme!='http'
            or origin.hostname not in {'127.0.0.1','localhost','::1'}):
        raise ValueError('Sample provisioning is available only in the local preview configuration.')
    path = Path(credentials_path).expanduser().resolve()
    if path.is_relative_to(APP_ROOT) or path.exists() or not path.parent.is_dir():
        raise ValueError('Use a new private credentials file outside the app source, in an existing folder.')
    password = secrets.token_urlsafe(24)
    hashed = generate_password_hash(password,method='scrypt')
    created_file = False
    with app.app_context():
        db = get_db()
        try:
            with db:
                db.execute('BEGIN IMMEDIATE')
                owner = db.execute("SELECT u.id FROM users u WHERE u.email=? AND u.account_kind='staff' AND EXISTS(SELECT 1 FROM memberships m WHERE m.user_id=u.id AND m.role='owner')",(owner_email.strip().lower(),)).fetchone()
                if not owner: raise ValueError('Choose an existing staff workspace owner.')
                if (db.execute("SELECT 1 FROM users WHERE email='sample.customer@kjancy.test'").fetchone()
                        or db.execute("SELECT 1 FROM workspaces WHERE name='Sample Customer Workspace'").fetchone()):
                    raise ValueError('The sample account or workspace already exists. Existing credentials are never overwritten.')
                wid,uid,lid,now = uuid.uuid4().hex,uuid.uuid4().hex,uuid.uuid4().hex,int(time.time())
                db.execute("INSERT INTO workspaces(id,name,public_id,created,contact_email,services_json,service_areas_json) VALUES(?,'Sample Customer Workspace',?,?,'support@sample.kjancy.test',?,?)",(wid,secrets.token_urlsafe(24),now,json.dumps(['HVAC','Plumbing','Electrical']),json.dumps(['Sample service area'])))
                db.execute("INSERT INTO memberships VALUES(?,?,'owner')",(wid,owner['id']))
                db.execute("INSERT INTO users(id,name,email,password_hash,created,account_kind) VALUES(?,'Sample Customer','sample.customer@kjancy.test',?,?,'customer')",(uid,hashed,now))
                db.execute("INSERT INTO customer_accounts(user_id,workspace_id,phone,location,completed_at) VALUES(?,?,'555-010-2040','19 Sample Street',?)",(uid,wid,now))
                db.execute("INSERT INTO leads(id,workspace_id,customer_user_id,customer_name,email,phone,service,location,message,created,updated,source) VALUES(?,?,?,'Sample Customer','sample.customer@kjancy.test','555-010-2040','HVAC','19 Sample Street','Fictional sample request: air conditioning inspection.',?,?,'customer_portal')",(lid,wid,uid,now,now))
                db.execute("INSERT INTO lead_events(lead_id,workspace_id,actor,description,created) VALUES(?,?,'Customer portal','Inquiry received',?)",(lid,wid,now))
                descriptor = os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                created_file = True
                with os.fdopen(descriptor,'w',encoding='utf-8') as file:
                    json.dump({'email':'sample.customer@kjancy.test','password':password,'login_url':app.config['PUBLIC_BASE_URL']+'/customer/login','business':'Sample Customer Workspace','note':'Local sample only. All sample records are fictional; no email was sent.'},file,indent=2)
        except BaseException:
            if created_file: path.unlink(missing_ok=True)
            raise
    return {'email':'sample.customer@kjancy.test','credentials_path':str(path),'business':'Sample Customer Workspace'}
