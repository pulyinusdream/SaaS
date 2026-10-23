# Customer Portal Implementation Plan

> **For agentic workers:** Execute inline using executing-plans/TDD; user approved scope and clarified end customers. No additional permission round. Request one fresh read-only whole-feature security review.

**Goal:** Customers can complete Get Started, submit service requests, view only their own requests and use a real sample account.
**Architecture:** Focused customers blueprint, account-kind/ownership extension, shared credentials/CSRF/lead persistence. Separate Admin/customer navigation. Explicit local sample command with generated private credentials.
**Tech stack:** Existing Flask/Jinja/SQLite/Waitress; no dependency.
**Spec:** ../../CUSTOMER-PORTAL.md

## Global constraints
Existing accounts default staff. Customer one-business profile/no memberships, all request queries customer+business scoped and explicit safe projection. No email-based legacy claiming, staff control or internal fields. Customer writes refresh active session/kind inside BEGIN IMMEDIATE; nonce submission idempotent1hour, profile versioned.25requests/page. Guest links/forms intact. Customer Get Started/Form move off Admin navigation; business setup remains owner-only in Settings. Sample is explicit/local/generated password/private file/isolated workspace; no existing record changes.

## Review focus
1. Customer gaining Admin through invitation, signup, membership or direct routes.
2. Other customer/tenant ID and email spoofing, guest retroactive claiming and private field leaks.
3. Revoked session/account kind between identity load/write; token replay/race/cross-account/filter scoping.
4. Stale contact/default service changes, genuine legacy migration and backup ownership retention.
5. Sample collision/retry/production refusal and sample data isolation.

## Tasks
- [x] **1 RED.** tests/test_customers.py with real temporary DB and clients. Observed17 missing-route failures; added/fixed a customer account-navigation regression.18 customer tests cover scope/ownership/projections/replay/profile/security/login/sample/migration.
- [x] **2 Server.** customers.py, sample_customer.py/create_sample_customer.py, schema/db migrations; role guard/home helper/auth/invite/account-return integration; ownership in lead persistence and portal inquiry setup evidence. Feature tests and final155-test suite green.
- [x] **3 UI implementation.** Customer signup/home/setup/form/detail templates and customer.css; shared shell/login/public form/Admin nav/inbox/settings/legacy setup. Desktop1440x900 fixture verified login, contact defaults, stale409, retained validation, saved request and detail. No credentials entered into new-password UI. Integration tests cover replay/status/isolation.
- [x] **4 Review/deliver.** Fresh read-only security review clean; full suite/compile/JS/pip/Taste passed. Verified backup/original-row baseline, local activation and additive sample under existing owner. Private credential handoff/docs/ZIP refreshed; own QA listener stopped. See evidence below for incomplete browser QA.

## Browser verification limit

- [ ] Tablet768, phone390 and narrow320, final focus/console/font inspection and screenshot export remain to be checked manually. Browser back after a POST produced ERR_CACHE_MISS/data-URL error; CUA URL policy blocked subsequent use of that QA tab. No alternative browser access was used to bypass this denial. Desktop screenshots were inspected inline only, and no new saved screenshot artifact is claimed. Closing/resetting the blocked temporary QA tab also failed; its4210 server was stopped. These are verification limitations, not completed checks.

No Git repository: baseline work/saas/pre-user-side-source.zip and ledger work/saas/customer-portal-progress.md replace commits/worktree. Preflight: source/customer identity must be server-set into existing lead row and unique submission key; profile business must match all safe projections; customer cannot obtain staff membership by invitation; backup sample create must preserve prior rows and keys.
