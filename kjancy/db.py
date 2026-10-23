import sqlite3
from contextlib import closing
from pathlib import Path

from flask import current_app, g


def connect(path):
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def get_db():
    if 'db' not in g:
        g.db = connect(current_app.config['DATABASE'])
    return g.db


def init_app(app):
    with closing(connect(app.config['DATABASE'])) as db:
        db.executescript(Path(__file__).with_name('schema.sql').read_text(encoding='utf-8'))
        with db:
            db.execute('BEGIN IMMEDIATE')
            columns = {row['name'] for row in db.execute('PRAGMA table_info(leads)')}
            for name, definition in (
                ('source', "TEXT NOT NULL DEFAULT 'service'"),
                ('business_name', "TEXT NOT NULL DEFAULT ''"),
                ('support_plan', "TEXT NOT NULL DEFAULT ''"),
                ('submission_key', 'TEXT'),
                ('assigned_user_id', 'TEXT REFERENCES users(id)'),
                ('customer_user_id', 'TEXT REFERENCES users(id)'),
                ('followup_action', "TEXT NOT NULL DEFAULT ''"),
                ('followup_due', 'INTEGER'),
                ('followup_completed_at', 'INTEGER'),
                ('followup_outcome', "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in columns:
                    db.execute(f'ALTER TABLE leads ADD COLUMN {name} {definition}')
            db.execute('CREATE UNIQUE INDEX IF NOT EXISTS leads_submission_key ON leads(submission_key)')
            db.execute('CREATE INDEX IF NOT EXISTS leads_assignment ON leads(workspace_id,assigned_user_id)')
            db.execute('CREATE INDEX IF NOT EXISTS leads_followup_due ON leads(workspace_id,followup_due)')
            db.execute('CREATE INDEX IF NOT EXISTS leads_customer ON leads(customer_user_id,workspace_id,created DESC)')
            workspace_columns = {row['name'] for row in db.execute('PRAGMA table_info(workspaces)')}
            if 'timezone' not in workspace_columns:
                db.execute("ALTER TABLE workspaces ADD COLUMN timezone TEXT NOT NULL DEFAULT 'UTC'")
            for name, definition in (
                ('contact_email', "TEXT NOT NULL DEFAULT ''"),
                ('contact_phone', "TEXT NOT NULL DEFAULT ''"),
                ('services_json', 'TEXT'),
                ('service_areas_json', "TEXT NOT NULL DEFAULT '[]'"),
                ('settings_version', 'INTEGER NOT NULL DEFAULT 1'),
                ('form_shared_at', 'INTEGER'),
            ):
                if name not in workspace_columns:
                    db.execute(f'ALTER TABLE workspaces ADD COLUMN {name} {definition}')
            user_columns = {row['name'] for row in db.execute('PRAGMA table_info(users)')}
            if 'email_verified_at' not in user_columns:
                db.execute('ALTER TABLE users ADD COLUMN email_verified_at INTEGER')
            if 'profile_version' not in user_columns:
                db.execute('ALTER TABLE users ADD COLUMN profile_version INTEGER NOT NULL DEFAULT 1')
            if 'account_kind' not in user_columns:
                db.execute("ALTER TABLE users ADD COLUMN account_kind TEXT NOT NULL DEFAULT 'staff' CHECK(account_kind IN ('staff','customer'))")
            message_columns = {row['name'] for row in db.execute('PRAGMA table_info(customer_request_messages)')}
            if 'sender_kind' not in message_columns:
                db.execute("ALTER TABLE customer_request_messages ADD COLUMN sender_kind TEXT NOT NULL DEFAULT 'customer' CHECK(sender_kind IN ('customer','staff'))")
            if 'staff_user_id' not in message_columns:
                db.execute('ALTER TABLE customer_request_messages ADD COLUMN staff_user_id TEXT REFERENCES users(id)')
            db.execute('CREATE INDEX IF NOT EXISTS customer_messages_direction ON customer_request_messages(workspace_id,sender_kind,lead_id,id)')

    @app.teardown_appcontext
    def close_db(_error=None):
        db = g.pop('db', None)
        if db is not None:
            db.close()
