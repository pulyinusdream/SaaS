import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, g, redirect, render_template, url_for
from werkzeug.exceptions import SecurityError

from . import account, account_settings, appointments, auth, business_settings, calendar_views, customers, customer_messages, db, followups, leads, mailer, reports, security, website, workspaces
from .validation import SERVICES, STATUSES


def create_app(config=None):
    app = Flask(__name__)
    app.config.update(
        DATA_DIR=os.environ.get('KJANCY_DATA_DIR', str(Path.home() / 'Documents' / 'Codex' / 'kjancy-data')),
        SECRET_KEY=os.environ.get('KJANCY_SECRET_KEY'), MAX_CONTENT_LENGTH=32 * 1024,
        MAX_FORM_MEMORY_SIZE=32 * 1024, MAX_FORM_PARTS=30,
        SESSION_COOKIE_NAME='kjancy_session', SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_SECURE=os.environ.get('KJANCY_HTTPS') == '1',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
        TRUSTED_HOSTS=['127.0.0.1', 'localhost', '[::1]'],
        ALLOW_OPAQUE_ORIGIN=False,
        MAIL_MODE=os.environ.get('KJANCY_MAIL_MODE', 'preview'),
        PUBLIC_BASE_URL=os.environ.get('KJANCY_PUBLIC_BASE_URL', 'http://127.0.0.1:4200'),
        MAIL_FROM=os.environ.get('KJANCY_MAIL_FROM', ''),
        SMTP_HOST=os.environ.get('KJANCY_SMTP_HOST', ''), SMTP_PORT=os.environ.get('KJANCY_SMTP_PORT', '587'),
        SMTP_USERNAME=os.environ.get('KJANCY_SMTP_USERNAME', ''), SMTP_PASSWORD=os.environ.get('KJANCY_SMTP_PASSWORD', ''),
        SMTP_SECURITY=os.environ.get('KJANCY_SMTP_SECURITY', 'starttls'),
    )
    app.config.update(config or {})
    data = Path(app.config['DATA_DIR']).resolve()
    data.mkdir(parents=True, exist_ok=True)
    app.config['DATABASE'] = str(data / 'kjancy.sqlite3')
    if not app.config['SECRET_KEY']:
        key_file = data / 'session.key'
        try:
            with key_file.open('xb') as file:
                file.write(secrets.token_bytes(48))
        except FileExistsError:
            pass
        app.config['SECRET_KEY'] = key_file.read_bytes()
    db.init_app(app)
    mailer.init_app(app)
    security.init_app(app)
    for blueprint in (auth.bp, account.bp, account_settings.bp, leads.bp, followups.bp, appointments.bp, calendar_views.bp, workspaces.bp, website.bp, business_settings.bp, reports.bp, customers.bp):
        app.register_blueprint(blueprint)

    @app.get('/')
    def index():
        return redirect(url_for(security.home_endpoint(g.user)), code=303)

    @app.get('/health')
    def health():
        db.get_db().execute('SELECT 1').fetchone()
        return {'status': 'ok'}

    @app.context_processor
    def shared_context():
        return {'statuses': STATUSES, 'services': SERVICES, 'mail_preview': app.config['MAIL_MODE'] == 'preview',
                'navigation_unread':customer_messages.unread_total()}

    app.add_template_filter(followups.format_due, 'due_time')

    @app.template_filter('timestamp')
    def timestamp(value):
        return datetime.fromtimestamp(value, timezone.utc).strftime('%b %d, %Y at %H:%M UTC')

    @app.template_filter('iso')
    def iso(value):
        return datetime.fromtimestamp(value, timezone.utc).isoformat()

    @app.template_filter('status_class')
    def status_class(value):
        return {'New': 'new', 'Contacted': 'contacted', 'Appointment booked': 'booked', 'Closed': 'closed'}.get(value, '')

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(410)
    @app.errorhandler(413)
    @app.errorhandler(429)
    @app.errorhandler(500)
    def error_page(error):
        if isinstance(error, SecurityError):
            return '<!doctype html><html lang="en"><title>Invalid host</title><h1>Invalid host</h1><p>Open this app at 127.0.0.1 or localhost.</p></html>', 400
        messages = {400: 'We could not verify that request.', 403: 'This action is not available to this account.', 404: 'We could not find that page.', 410: 'This link is no longer available.', 413: 'That request is too large.', 429: 'Let’s pause for a moment.', 500: 'We could not finish that action.'}
        return render_template('error.html', title=messages.get(error.code, 'Something went wrong'), error=error), error.code

    return app
