# Customer follow-up messages

The customer can open a request from My requests, send a plain-text follow-up, and see their sent messages. Business staff see the same messages on the matching Admin request and a message-count link in the inbox. This is one-way customer messaging; it does not send email, change status, book an appointment, or expose internal notes.

Extend the current Flask/Jinja/SQLite implementation and mint design. Use a separate append-only customer_request_messages table rather than mixing public messages with private staff events. Enforce current session, customer ownership and business scope inside the write transaction. Preserve request identity, version, status and contact snapshots. Validate 1–2000 characters, CSRF/origin, signed hour-long submission tokens bound to customer/business/request, replay protection and rate limiting. Allow follow-ups on closed requests without reopening them. Render escaped multiline text; newest first, 25 per page.

## Implementation and checks

- [x] Write failing integration tests for delivery to the correct Admin, ownership/business isolation, invalid content, replay, expired or swapped tokens, authorization and pagination.
- [x] Add additive schema, message context helpers, customer POST handler, shared message history, customer compose form, and inbox message link.
- [x] Run focused and complete tests; compile Python and check existing JS/dependencies. Obtain an independent read-only security and behavior review.
- [x] Exercise customer submission and Admin rendering in an isolated browser fixture at desktop and phone widths. Preserve live records, back up before additive migration/restart, verify live UI read-only and refresh the source archive.

## Review focus

Another customer cannot post to or read a request. Another business cannot see messages. Invalid or duplicate submissions cannot create extra messages/events. HTML is text. Message errors retain input without exposing internal notes. Existing status/notes forms remain usable and request versions do not change on message receipt. No external email is implied.
