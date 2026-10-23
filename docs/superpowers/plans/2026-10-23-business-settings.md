# Business Settings Implementation Plan

> **For agentic workers:** Execute inline with executing-plans and test-driven-development. The user approved this milestone and asked to implement it; no repeated approval round. Request one fresh read-only whole-feature review at completion.

**Goal:** Each owner can configure a business and follow an honest setup checklist.
**Architecture:** Additive workspace columns, focused settings service/routes, per-workspace service validation, scoped checklist projection, reusable Jinja form controls.
**Tech Stack:** Existing Flask/SQLite/Waitress, Jinja, vanilla JS/CSS; no new dependency.
**Spec:** ../../BUSINESS-SETTINGS.md

## Global constraints

Owner writes recheck role/membership under BEGIN IMMEDIATE; settings_version guards lost changes. All service lead inserts validate the current workspace catalogue under the same write lock. Historical customer fields never change. Service areas guide customers; free-form address entry remains. Defaults preserve six legacy choices but do not fabricate contact, areas or completed setup. Preserve existing business rules, tenant-bound CSRF, mint design and local-only operation.

## Review focus

1. Stale settings/timezone interactions: regression tests reject stale versions and preserve saved instants.
2. Revoked owner after identity loading: before-request synthetic demotion must block settings/sharing writes.
3. Removed service on already-open form: reject new request with a clear field error; preserve previous leads.
4. Foreign settings/form/checklist identifiers: selected authenticated workspace or public URL controls scope.
5. False setup progress: manual leads and pending invites must not count as received public inquiry/active teammate.

## Tasks

- [x] **1. RED:** Create tests/test_business_settings.py using existing real-client fixture helpers and isolated SQLite. Assert persistence/public exposure, defaults, validation bounds, versions/timezone, owner/CSRF/tenant scope, changed services, actual setup progression, optional-team state, migration and backup retention. Run missing-route/column tests before implementation.
- [x] **2. Backend:** db.py adds contact_email/contact_phone/services_json/service_areas_json/settings_version/form_shared_at. New business_settings.py supplies service_choices(workspace), service_areas(workspace), setup_state(workspace), settings and setup routes. Register blueprint; lead_values(form,services=SERVICES) keeps old default signature. leads.new/public_request pass scoped choices, validate under write lock and render matching choices/areas/contact. Existing timezone endpoint participates in settings version/owner checks. Targeted and full tests pass.
- [x] **3. Interface:** New business_settings.html/setup.html; owner navigation links/SVG icons; inbox setup notice; inquiry context/choices from saved settings. Existing macros accept explicit service choices, leaving marketing trade categories unchanged. Scoped CSS extends frame; verify browser save/errors/stale/real inquiry/checklist/copy fallback on synthetic data at desktop/tablet390/320 with keyboard and overflow checks.
- [x] **4. Review/deliver:** Fresh read-only feature review, reproduce/fix important findings, full tests/compilation/JS/dependency/Taste checks. Private verified backup and fresh existing-column hashes before actual activation. Restart loopback server, compare original data and health, update README/VERIFICATION and clean104+ source ZIP. Save labelled QA screenshots, show real settings/setup when browser policy permits.

No Git repository exists (verified with git rev-parse); continue in the existing generated project with source snapshot/private ledger instead of a worktree/commit.
