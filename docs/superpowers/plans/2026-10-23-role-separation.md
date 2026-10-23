# Admin and Customer Separation Implementation Plan

> Execute inline with executing-plans/TDD. User requested inspection and separation, and explicitly permits routine implementation choices without additional questions. One fresh read-only reviewer at the end. No Git repository: work/saas/pre-role-separation-source.zip is the baseline.

**Goal:** Admin manages the business; customers request service and track only their own requests. Role-specific entry points must not silently sign into the other role.
**Architecture:** Preserve server-stored staff/customer kinds, existing tenant/ownership guards and shared personal security controls. Tighten entry/recovery routing and turn the existing guest-form view into a read-only preview for staff. No new schema, dependencies or credentials.
**Stack:** Flask/Jinja/SQLite, existing mint framed-sheet design and IBM Plex Sans.

## Design and findings

Both login URLs currently accept either kind of credentials; authenticated visits silently return to the current home. Anonymous customer pages redirect to Admin login. The public request form remains writable for staff and signed-in customers, allowing guest submissions outside customer history. Recovery/verification returns customers to Admin login. These entry points explain visible functional overlap despite existing Admin-route authorization.

Use role-specific login checks, a clear wrong-portal page with CSRF-protected explicit sign-out/switch, read-only staff previews, and customer redirection only to their own business form. Reject all authenticated guest-form POSTs; anonymous guest forms stay usable. Admin may record incoming leads on behalf of customers with its existing Add lead function. Personal name/password/session/email controls intentionally remain shared and account-scoped. Owner Business setup configures the business and stays separate from personal customer Get started. Retain Admin registration, guest links, internal processing and marketing controls.

## Access matrix

| Function | Admin/staff | Customer | Guest |
| --- | --- | --- | --- |
| Business inbox/calendar/team | Existing membership and role | Denied | Sign in |
| Business settings/reports/setup | Owner only | Denied | Sign in |
| Customer Get started/form/history | Denied | Own account/business only | Customer sign in |
| Public guest service form | Read-only preview | Own business redirects to owned form; other business denied | Submit guest inquiry |
| Personal account/security | Own account only | Own account only | Recovery/verification only |
| Sign in | Admin login only | Customer login only | Choose intended portal |

## Execution

- [x] RED: nine real integration regressions reproduced role entry/form/routing overlap. Fixed MIME-decoding/request-context fixture errors. A reviewer-found verification Back link also had a failing regression before correction.
- [x] GREEN: modified auth/security/account/leads/customers; added portal_mismatch.html and read-only inquiry preview; role-aware recovery links and shell labels. Preserved CSRF, uniform unknown-account responses and current sessions until explicit logout.
- [x] Verify: final164 tests passed132.298s; compile/JS/pip/Taste passed. Independent reviewer found no important regressions; minor verification link corrected. Desktop1440 Customer/Admin and preview, Customer390 history/form,320/768 form and390 Admin preview checked with no horizontal overflow; phone Escape focus/fonts/console checked. Saved sample-only screenshots.
- [x] Deliver: verified backup and all original rows across12tables preserved, installed app restarted4200 and anonymous role redirects/health confirmed. README/spec/verification and source ZIP refreshed. QA tab closed/viewport reset/listener4211 stopped. No real accounts changed or external deployment/email.

## Review focus

Wrong-role POST must not create or revoke sessions. A selected portal is only a routing hint and cannot change account kind, business or authorization. Authenticated public-form POSTs cannot create unowned/cross-business requests. Logout switch accepts only fixed internal destinations and remains POST/CSRF-protected. Reset/verification follows the token account's role, without revealing account existence during recovery. Strict email verification and original staff/customer route guards remain enforced.
