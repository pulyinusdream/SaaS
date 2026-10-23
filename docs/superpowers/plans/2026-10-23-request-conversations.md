# Request conversations and unread messages

User approved Admin replies, shared customer/staff history and unread indicators. Extend the existing Flask/Jinja/SQLite customer follow-up feature in place, retaining mint styling and private staff notes.

## Decisions and boundaries

- Extend customer_request_messages with sender_kind (legacy rows default customer) and staff_user_id. customer_user_id continues to identify the request's customer for both directions. Staff replies require a current customer-linked request in the active business; guest requests use existing contact details instead.
- Add per-user, per-message read receipts. GET requests never mark messages read. Each history page has a signed, scoped **Mark displayed messages as read** POST for at most 25 displayed messages from the other side. Reading one page does not clear hidden pages or newly arriving messages. Staff read state is individual, not shared among the team.
- Unread badges appear on customer request rows, Admin inbox rows and each role's navigation. Counts use only the current business and owned customer requests. Refresh to update; no external notifications or polling dependency.
- Admin replies are explicitly customer-visible; staff notes/reminders remain private. Preserve request status, version, identity, appointment and legacy message data. Reply tokens are signed, hour-long, bound to sender/business/request, with atomic duplicate protection, CSRF/origin and rate limits. Closed requests still accept messages without reopening.

## Tasks

- [x] Write failing real Flask/SQLite integration tests for staff delivery, invalid input, security scopes, duplicate/concurrent sends, unread direction/user isolation, read-token scope, pagination/new arrival preservation, and additive migration.
- [x] Add schema migration/read receipts and message helpers in schema.sql, db.py and customer_messages.py; extend customers.py and leads.py with protected read/reply endpoints. Update list queries and base context for unread counts.
- [x] Extend shared history with sender roles, unread labels and read action; add a clearly labelled Admin reply form and role-specific unread list/navigation badges. Retain existing customer send forms and Admin status/notes actions.
- [x] Verify focused tests, full suite, compile/dependencies, JS syntax and scoped interface lint. Request independent read-only review. Exercise both directions and unread actions in an isolated browser fixture, including phone layout.
- [x] Back up live data, capture original-row hashes, activate additive migration with an owned server restart, check health and current UI without submitting live test messages, verify unchanged original data, update docs/archive and clean up QA.

## Review focus

Other customer/business/staff scopes cannot disclose or write messages/read state. A staff session, membership or recipient profile changed after initial identity loading is rechecked inside the write transaction. Tokens cannot be swapped between accounts, requests, roles or read/send actions. Concurrent replay produces one reply/event. Per-message receipts preserve unread messages on unseen pages and those arriving after the signed page snapshot. Reading and replies never expose private notes or mutate request/appointment state.
