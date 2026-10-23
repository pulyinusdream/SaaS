PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL,
 password_hash TEXT NOT NULL, created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS workspaces (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, public_id TEXT UNIQUE NOT NULL, created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS memberships (
 workspace_id TEXT NOT NULL REFERENCES workspaces(id), user_id TEXT NOT NULL REFERENCES users(id),
 role TEXT NOT NULL CHECK(role IN ('owner','dispatcher')), PRIMARY KEY(workspace_id,user_id)
);
CREATE TABLE IF NOT EXISTS customer_accounts (
 user_id TEXT PRIMARY KEY REFERENCES users(id), workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 phone TEXT NOT NULL DEFAULT '', location TEXT NOT NULL DEFAULT '',
 version INTEGER NOT NULL DEFAULT 1, completed_at INTEGER
);
CREATE TABLE IF NOT EXISTS sessions (
 digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), expires INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS sessions_user_expiry ON sessions(user_id,expires);
CREATE TABLE IF NOT EXISTS session_details (
 digest TEXT PRIMARY KEY REFERENCES sessions(digest) ON DELETE CASCADE,
 created INTEGER NOT NULL, client TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS leads (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 customer_name TEXT NOT NULL, email TEXT NOT NULL DEFAULT '', phone TEXT NOT NULL DEFAULT '',
 service TEXT NOT NULL, location TEXT NOT NULL, message TEXT NOT NULL DEFAULT '',
 status TEXT NOT NULL DEFAULT 'New' CHECK(status IN ('New','Contacted','Appointment booked','Closed')),
 internal_notes TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 1,
 created INTEGER NOT NULL, updated INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS leads_workspace_created ON leads(workspace_id,created DESC);
CREATE TABLE IF NOT EXISTS lead_events (
 id INTEGER PRIMARY KEY, lead_id TEXT NOT NULL REFERENCES leads(id), workspace_id TEXT NOT NULL REFERENCES workspaces(id),
 actor TEXT NOT NULL, description TEXT NOT NULL, created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS invitations (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), email TEXT NOT NULL,
 token_digest TEXT UNIQUE NOT NULL, expires INTEGER NOT NULL, used INTEGER NOT NULL DEFAULT 0,
 created INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS rate_limits (
 bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS account_tokens (
 digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id),
 purpose TEXT NOT NULL CHECK(purpose IN ('verify','reset')), email TEXT NOT NULL,
 credential_digest TEXT NOT NULL, created INTEGER NOT NULL, expires INTEGER NOT NULL, used INTEGER
);
CREATE INDEX IF NOT EXISTS account_tokens_user_purpose ON account_tokens(user_id,purpose,created);
CREATE UNIQUE INDEX IF NOT EXISTS leads_identity_workspace ON leads(id,workspace_id);
CREATE TABLE IF NOT EXISTS customer_request_messages (
 id INTEGER PRIMARY KEY, lead_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
 customer_user_id TEXT NOT NULL REFERENCES users(id), sender_name TEXT NOT NULL,
 sender_kind TEXT NOT NULL DEFAULT 'customer' CHECK(sender_kind IN ('customer','staff')),
 staff_user_id TEXT REFERENCES users(id),
 body TEXT NOT NULL CHECK(length(body) BETWEEN 1 AND 2000),
 submission_key TEXT UNIQUE NOT NULL, created INTEGER NOT NULL,
 FOREIGN KEY(lead_id,workspace_id) REFERENCES leads(id,workspace_id)
);
CREATE INDEX IF NOT EXISTS customer_messages_request ON customer_request_messages(workspace_id,lead_id,created DESC,id DESC);
CREATE TABLE IF NOT EXISTS request_message_reads (
 user_id TEXT NOT NULL REFERENCES users(id), message_id INTEGER NOT NULL REFERENCES customer_request_messages(id),
 PRIMARY KEY(user_id,message_id)
);
CREATE TABLE IF NOT EXISTS appointments (
 id TEXT PRIMARY KEY, workspace_id TEXT NOT NULL REFERENCES workspaces(id), lead_id TEXT NOT NULL,
 assigned_user_id TEXT REFERENCES users(id), start_at INTEGER NOT NULL, end_at INTEGER NOT NULL,
 state TEXT NOT NULL DEFAULT 'scheduled' CHECK(state IN ('scheduled','cancelled')),
 cancellation_reason TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL, updated INTEGER NOT NULL,
 FOREIGN KEY(lead_id,workspace_id) REFERENCES leads(id,workspace_id),
 CHECK(end_at>start_at AND end_at-start_at BETWEEN 900 AND 28800 AND (end_at-start_at)%900=0)
);
CREATE UNIQUE INDEX IF NOT EXISTS appointments_active_lead ON appointments(lead_id) WHERE state='scheduled';
CREATE INDEX IF NOT EXISTS appointments_window ON appointments(workspace_id,state,start_at,end_at);
CREATE INDEX IF NOT EXISTS appointments_teammate ON appointments(workspace_id,assigned_user_id,start_at,end_at);
