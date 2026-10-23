# Email verification and recovery

The user approved this milestone and confirmed there is no SMTP service yet. Extend the existing Flask/SQLite account flow and mint interface. Do not deploy, purchase services, send real emails, or claim mailbox delivery.

Architecture: one account-token table stores random token digests, purpose, expiry and email binding. Confirmation GETs are read-only; CSRF-protected POSTs atomically claim tokens. Verification lasts 24 hours; password-reset links last 30 minutes. A reset updates the scrypt password, invalidates all outstanding account tokens and revokes all sessions in one transaction. Never sign in automatically after a reset. Never mark old accounts verified during migration.

Mail transport: durable private `.eml` files outside published source. Default preview mode writes files only; it never sends mail and never exposes a public preview/link endpoint. SMTP mode queues the same files, and a single loopback runner worker sends using verified TLS (STARTTLS or SSL), retries temporary failures and removes sent/expired files. SMTP credentials come only from environment variables. Links use a configured base URL, not request Host headers. Invalid SMTP configuration fails startup. Public origins cannot use preview mode. Verification is required on private workspace routes in SMTP mode; preview mode displays its exception explicitly and preserves current local workspace access.

User flows: login links to Forgot password; reset request gives the same generic receipt for known/unknown addresses, without provider calls in the request path. Signed-in users see actual verification state and can request a replacement link. Resending supersedes older links. Validate confirmation/password errors without consuming a valid token. Existing workspace and lead records remain unchanged.

Implementation (inline, existing generated directory has no Git repository):

- [x] Write and observe failing integration tests for verification, scanner-safe GET, token scope/expiry/reuse/replacement, recovery validation and revocation, unknown addresses, CSRF, strict-mode access and old-data upgrade.
- [x] Implement additive migration, private durable mail queue, TLS transport/config checks, account routes, signup/login hooks and strict-mode guards.
- [x] Extend existing auth templates and shell with accessible status, error, pending and success states; add local preview helper and SMTP setup instructions.
- [x] Run the whole suite and syntax checks; obtain a fresh security review; test browser flow using synthetic accounts and a distinct QA cookie/data directory. Never change a real user's password.
- [x] Back up/check existing data, activate the local release, package source without tokens/data/credentials and show the finished recovery screen.

Review focus: token purpose/email binding; concurrent claims; invalid form must not burn link; uniform unknown-account response; password changes revoke sessions; preview messages never web-accessible; fixed-origin URLs and TLS fail closed.

Security references: [OWASP recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html), [Python SMTP/TLS API](https://docs.python.org/3/library/smtplib.html). Hosting, DNS sender verification, real mailbox delivery and operational monitoring remain outside this local milestone.

Completed: final46-test suite, browser views, review regressions, stored-data preservation, source package and SMTP setup guide.
