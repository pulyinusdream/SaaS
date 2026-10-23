# Account Settings and Session Security Implementation Plan

> **For agentic workers:** Execute inline with executing-plans and test-driven-development. The user approved the proposed feature and asked to implement; do not restart approval rounds. Obtain one fresh read-only whole-feature review before delivery.

**Goal:** Every signed-in user can manage their own profile, password and other sessions.
**Architecture:** Focused account_settings blueprint reuses existing auth/session/CSRF/rate-limit facilities. Add a profile version and optional cascading session metadata; preserve session-token/hash and fixed8-hour expiry contracts.
**Tech Stack:** Flask/Jinja/SQLite, standard library and existing Werkzeug; no dependency.
**Spec:** ../../ACCOUNT-SECURITY.md

## Global constraints
Personal-account scope; current session rechecked inside write transaction. Profile1–100/control-free, stale409. Password12–128/different/confirmed/current reauthentication;10attempts/15min. Password change revokes all sessions/account links and signs out current browser. Bulk other-session revocation preserves current; no arbitrary user ID target. New metadata optional/legacy honest,25sessions/page, UTC times, no raw token/digest/UA/IP output. Preserve mint accessibility/security/user data; no real credential mutation for QA.

## Review focus
1. Revoked/expired session after identity load must not write.
2. Password check races with reset/change and concurrent password changes must not revive stale access.
3. Other-user IDs, expired sessions, unverified/no-workspace accounts and strict verification gates.
4. Legacy sessions, browser labels, pagination/no secrets, backup cascade and idempotent migration.
5. Invalid/stale profile and password fields never clobber data or echo credentials.

## Tasks
- [x] **1. RED tests.** Create tests/test_account_settings.py; real isolated request/DB assertions for the spec's security, persistence, validation, concurrency, metadata, migration and recovery cases. Run from app directory; expect missing /account/settings routes to fail before implementation.
- [x] **2. Server.** New account_settings.py blueprint with consistent reads, refreshed account under write transaction, profile versioning, password reauthentication and bulk session revocation. Modify db.py/schema.sql (profile_version/session_details/index), security.py (session label/details and self-service verification exemptions), backup.py (foreign keys on restore), __init__.py registration. Make feature/full suite green.
- [x] **3. Interface.** account_settings.html/account-settings.css, existing shell nav/icon integration. Three anchored forms/sections, paged honest sessions and focused failures. Browser QA with isolated credentials/data: profile success/stale/error, reauthenticate/revoke other fixture sessions, inspect password labels/native-required behavior without entering a new credential, desktop/tablet390/320/focus/overflow/console.
- [x] **4. Review and deliver.** Fresh read-only reviewer, reproduce/fix important findings test-first, complete full tests/compile/JS/pip/Taste. Private online backup/hash baseline before real activation, compare original values after local restart/health/view; update docs/ledger/ZIP, save screenshot, reset viewport and close/stop QA.

No Git repository is present. The source ZIP snapshot and work/saas/account-security-progress.md replace commits/worktree. Preserve the121-test Reports release as baseline. Shared interface preflight: session_details attaches to existing session digest and cascades on deletion; restore must enable FK, active_account must refresh the same credential used by reauthentication; profile version gates the account user only. Template renders explicit metadata, never session hashes.
