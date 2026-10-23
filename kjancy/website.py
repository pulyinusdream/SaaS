"""Serve the connected marketing site and accept workspace-scoped walkthroughs."""
from pathlib import Path
import secrets
import sqlite3

from flask import Blueprint, abort, current_app, redirect, render_template, request, send_from_directory, session, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .db import get_db
from .leads import create_lead
from .security import csrf_token, digest, rate_limit
from .validation import SERVICES, email, text

bp = Blueprint('website', __name__)
PLANS = ('Not sure yet', 'Lead Booking System', 'Dedicated Dispatcher System')
PAGES = {'index.html', 'privacy.html', 'websites.html', 'lead-follow-up.html', 'dispatch-support.html', '404.html'}


def site_root():
    return Path(current_app.root_path).parent / 'marketing'


def business_for(public_id):
    business = get_db().execute('SELECT id,name,public_id FROM workspaces WHERE public_id=?', (public_id,)).fetchone()
    if not business:
        abort(404)
    return business


def signer():
    return URLSafeTimedSerializer(current_app.secret_key, salt='website-walkthrough-v1')


def render_site(business, *, values=None, errors=None, received=False):
    root = site_root()
    if not (root / 'index.html').is_file():
        abort(503)
    source = (root / 'index.html').read_text(encoding='utf-8')
    start, marker, tail = source.partition('<form class="contact-form" id="walkthrough-form" novalidate>')
    _, end, suffix = tail.partition('</form>')
    if not marker or not end:
        abort(503)
    csrf_token()  # Establish the browser nonce before signing a submission.
    submission = signer().dumps({'workspace': business['id'], 'browser': session['_csrf'], 'nonce': secrets.token_urlsafe(24)})
    fragment = render_template('website_success.html' if received else 'website_form.html', business=business, values=values or {}, errors=errors or {}, plans=PLANS, submission_token=submission)
    page = start + fragment + suffix
    # On a phone the contact introduction precedes the form by a full screen.
    # Send the primary CTA directly to the actionable form (or saved receipt).
    return page.replace('href="#contact"', f'href="#{"walkthrough-success" if received else "walkthrough-form"}"')


def walkthrough_values(form):
    errors = {}
    values = {name: text(form, name, limit, errors, required=required, label=label) for name, limit, required, label in (
        ('name', 100, True, 'your name'), ('company', 150, True, 'business name'),
        ('email', 200, True, 'email address'), ('trade', 60, True, 'trade'),
        ('plan', 60, True, 'package interest'), ('message', 2000, False, 'message'),
    )}
    if not email(values['email']):
        errors['email'] = 'Enter a valid email address.'
    if values['trade'] not in SERVICES:
        errors['trade'] = 'Choose a trade from the list.'
    if values['plan'] not in PLANS:
        errors['plan'] = 'Choose one of the available packages, or Help me choose.'
    return values, errors


@bp.route('/website/<public_id>/', methods=['GET', 'POST'])
def home(public_id):
    business = business_for(public_id)
    values, errors = {}, {}
    if request.method == 'POST':
        rate_limit(f'website-walkthrough:{business["id"]}', 20, 3600)
        if request.form.get('website_url', ''):
            abort(400, description='This request could not be verified.')
        try:
            token = request.form.get('submission_token', '')
            signed = signer().loads(token, max_age=7200)
            if (not isinstance(signed, dict) or signed.get('workspace') != business['id']
                    or signed.get('browser') != session.get('_csrf') or not signed.get('nonce')):
                raise BadSignature('Wrong submission context')
        except (BadSignature, SignatureExpired):
            abort(400, description='This form expired or could not be verified. Reopen the website form and try again.')
        values, errors = walkthrough_values(request.form)
        if not errors:
            key = digest(token)
            existing = get_db().execute('SELECT id FROM leads WHERE workspace_id=? AND submission_key=?', (business['id'], key)).fetchone()
            if not existing:
                lead = {'customer_name': values['name'], 'business_name': values['company'], 'email': values['email'],
                        'phone': '', 'service': values['trade'], 'support_plan': values['plan'], 'location': '',
                        'message': values['message'], 'source': 'website_walkthrough', 'submission_key': key}
                try:
                    create_lead(business, lead, 'Website walkthrough form')
                except sqlite3.IntegrityError:
                    # Two concurrent POSTs can race the initial lookup; the unique
                    # key and transaction keep both lead and activity single-use.
                    if not get_db().execute('SELECT id FROM leads WHERE workspace_id=? AND submission_key=?', (business['id'], key)).fetchone():
                        raise
            session['walkthrough_received'] = public_id
            return redirect(url_for('website.received', public_id=public_id) + '#walkthrough-success', code=303)
    return render_site(business, values=values, errors=errors), 422 if errors else 200


@bp.get('/website/<public_id>/received')
def received(public_id):
    business = business_for(public_id)
    if session.get('walkthrough_received') != public_id:
        return redirect(url_for('website.home', public_id=public_id) + '#contact', code=303)
    return render_site(business, received=True)


@bp.get('/website/<public_id>/<path:filename>')
def page(public_id, filename):
    business = business_for(public_id)
    if filename == 'index.html':
        return home(public_id)
    if filename.startswith('assets/'):
        return send_from_directory(site_root(), filename)
    if filename not in PAGES:
        abort(404)
    if filename == 'privacy.html':
        source = (site_root() / filename).read_text(encoding='utf-8')
        start, marker, tail = source.partition('<h2>Your walkthrough request</h2>')
        _, end, suffix = tail.partition('<h2>The website chat</h2>')
        if not marker or not end:
            abort(503)
        privacy = render_template('website_privacy.html', business=business)
        source = start + privacy + end + suffix
        # Replace only the static-only policy paragraphs; retain credits and scope.
        copy_start, copy_marker, copy_tail = source.partition('<h2>Copying and downloading</h2>')
        _, cookie_end, cookie_tail = copy_tail.partition('<h2>Illustrative examples</h2>')
        if copy_marker and cookie_end:
            source = copy_start + render_template('website_cookies.html') + cookie_end + cookie_tail
        source = source.replace('This notice describes the current website; a future CRM connection or other collection method will require an updated notice.', 'For requests submitted here, contact the receiving business identified above to discuss your saved information.')
        return source
    return send_from_directory(site_root(), filename)
