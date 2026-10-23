# Deployment and backups implementation plan

The user chose to prepare deployment and backups first, with no hosting purchase or publication. Preserve the local app, stored accounts/leads and current email preview. No new business feature or redesign.

Architecture: keep Flask/SQLite/Waitress. Add a separate hosting runner with validated HTTPS origin, exact trusted proxy, secure cookies, disabled opaque-origin preview compatibility, SMTP-only mail and an explicitly configured external data directory. Invalid settings fail before creating data or listening. A container blueprint runs one non-root app process with a named data volume and loopback-only published port behind a future TLS proxy. Its defaults intentionally do not permit deployment without the missing SMTP/hosting settings.

Backups: use SQLite's online backup API, including committed WAL writes. A private ZIP contains a verified SQLite snapshot and a versioned SHA256 manifest, but excludes signing keys, preview emails and environment credentials. Verification checks the archive members, size, checksum, SQLite integrity, required schema and foreign keys. Restore only into a new, empty destination outside application source; never replace live data. Restore clears sessions/account tokens, revokes invitations and creates a new signing key so old bearer links cannot revive. Customer passwords, workspaces and lead records remain usable. No automatic deletion or scheduled service is introduced.

Approaches considered: publishing the current preview would expose a development-only email ownership exception; rebuilding on another hosting runtime would discard working code. A separate validated runner plus backup/recovery tooling prepares the existing app without either change. Actual hosting, domain purchase and SMTP remain deferred by the user.

Implementation, using planning/test-first skills and inline execution:

- [x] Write failing tests for WAL-consistent backups, checksum/invalid archive rejection, safe new-directory restore, revoked ephemeral credentials, invalid hosting config and HTTPS enforcement.
- [x] Implement focused `kjancy/backup.py`, `backup.py`, `kjancy/deployment.py`, `serve.py` and hosting-only HTTPS gate. Keep the local runner behavior unchanged.
- [x] Add Dockerfile, .dockerignore, compose blueprint, safe environment example, local backup launcher and operator runbook. Validate container config and build/run if Docker is available.
- [x] Run the complete application suite, real backup/restore drills on isolated data, source checks and fresh correctness/security review. Create and verify one private backup of existing data without restoring or editing it.
- [x] Package the updated source and report actual checks, private backup location and untested/deferred hosting requirements.

Review focus: no overwrite/path traversal/archive bombs; committed WAL data retained; restore cannot revive used account tokens; production cannot use preview/HTTP/wildcard proxy; health stays minimal and available; Docker source excludes all runtime data/secrets.

No Git repository exists in this generated project. Private test data and backups live outside published source and ZIPs. Authoritative references: https://docs.python.org/3/library/sqlite3.html and https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html.

Completed preparation: 52 tests passed; private backup verified; Compose parsed. Container build/runtime, live TLS and SMTP remain unverified and deferred.
