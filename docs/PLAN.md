# KJAncy account and lead inbox implementation plan

Goal: a business signs up, receives a real service inquiry, and manages that lead in its own workspace. Two businesses cannot read or change one another's records. The user approved this scope and requested a second browser tab.

Architecture: Flask application, SQLite persistence, server-rendered Jinja templates, progressive vanilla JavaScript, Waitress bound to loopback. Python dependencies live in an isolated environment. Runtime data and signing key live outside the source folder. This is a working local first release, not a public cloud deployment.

Scope: owner registration/login/logout; persistent, revocable sessions; business-scoped lead list/search/status filters and detail updates; public company inquiry form; owner-created, expiring, single-use dispatcher invitations; workspace selection for invited staff. Four lead states: New, Contacted, Appointment booked, Closed. Appointment booked records a staff-entered status, not an external calendar reservation.

Constraints: preserve existing marketing files. No demo users or fake metrics in the delivered database. Hash passwords; validate forms on the server; protect all writes with CSRF; use parameterized SQL; resolve tenant access from membership on every request; expire invitations and sessions; avoid storing credentials in source. Do not add billing, calling, external AI, email sending or public hosting to this milestone.

Design: Taste Skill framed-sheet, seed 716491800. Pale mint L-frame, white work surface, IBM Plex Sans, quiet sidebar, restrained status colour, no decorative charts or metric tiles. Inbox question: who needs a reply? The lead's service and customer handoff are the signature element. Mobile uses a collapsible navigation and stacked lead rows. UI UX Pro Max informs form validation, focus, contrast and touch targets; the dealt application composition takes precedence over marketing-oriented search results.

## Tasks

- [x] 1. Establish failing integration tests for registration and cross-company isolation using temporary SQLite databases and real HTTP-style Flask clients.
- [x] 2. Implement schema, app factory, password hashing, authentication, CSRF, request bounds, rate limiting and security headers. Verify registration, invalid credentials, logout revocation and persistence.
- [x] 3. Implement tenant-scoped lead capture/list/detail/update, status/search filters and optimistic concurrency. Test malicious tenant IDs, unauthorized direct URLs, invalid inputs, HTML escaping and stale updates.
- [x] 4. Implement workspace membership and single-use dispatcher invites with expiry and revocation. Test owner-only controls, assignment boundaries and token reuse.
- [x] 5. Build complete responsive templates and states: signup/login, empty inbox, inquiry, populated inbox, detail, team, invitations, workspace selection and errors. Wire actual actions and keyboard focus.
- [x] 6. Run complete tests, syntax/source checks and browser QA at desktop/tablet/phone sizes. Review security boundaries, fix findings, and save screenshots.
- [x] 7. Provide launch instructions, pinned requirements, verification limitations and a clean source ZIP. Start the clean local app and open it visibly in a second tab, preserving the existing website tab.

Review focus: cross-tenant read/write attempts; forged/replayed writes; stale concurrent edits; invitation expiry/reuse; validation and no-script form behaviour. All are tested at the route/database boundary. No Git repository exists in this generated project, so source snapshots and this plan replace worktree/commit steps.

Execution: inline, continuing under the user's explicit instruction to create the agreed milestone. A fresh reviewer examines the security and correctness boundaries before delivery.
