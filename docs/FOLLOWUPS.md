# Lead assignment and follow-up implementation plan

> **For agentic workers:** Use executing-plans for inline implementation. The user approved the five-item assignment/follow-up scope and asked to work on it. Continue without another approval round.

**Goal:** Give each workspace a real daily queue: responsible teammate, next action, due time, completion outcome and activity history.

**Architecture:** Extend Flask/SQLite/Jinja and the existing mint framed-sheet interface. Keep status/notes writes compatible; add a separately versioned POST workflow using the same lead version and company-bound CSRF. Store due instants as UTC epochs. A workspace timezone (default UTC, clearly shown and owner-editable) determines entry/display and local-day boundaries. Use Python zoneinfo with pinned first-party tzdata for Windows. No SMTP, scheduler, polling or simulated reminders: current saved work is calculated on page load/refresh.

**Tech Stack:** Existing Flask, SQLite, Waitress, self-hosted IBM Plex Sans and progressive JavaScript; add only tzdata for timezone rules.

**Spec:** The five-item scope accepted in the conversation; this document records implementation choices.

## Global constraints and design

- Preserve existing accounts, lead fields, website capture, sessions and role permissions. Both owners and dispatchers already manage workspace leads and may manage assignments/follow-ups. Assignment does not restrict other members' existing visibility.
- Assignees must be current members of the same workspace, including its owner. Removing a dispatcher atomically unassigns affected leads, increments versions and records activity.
- One current follow-up per lead: action up to 240 characters, due instant, optional completion state/outcome up to 1000 characters. Scheduling requires action and due together; clearing requires both blank. Completing requires a pending follow-up and an outcome. Rescheduling resets completion. Stale submissions receive 409 and never overwrite.
- Closed leads retain their follow-up history but do not generate Due today/Overdue reminders. Reopening resumes a pending follow-up. Past dates are accepted and clearly become overdue.
- Due today means the entire workspace-local calendar day; Overdue means pending due strictly before now. They can overlap. Completed and closed leads are excluded from both. My leads and Unassigned include all statuses, with status/search filters available.
- A teammate's removal, invalid/foreign lead/member IDs, CSRF failure, partial or malformed dates, invalid timezone, DST gaps/ambiguous wall times and stale forms must never silently write incorrect work. Ambiguous/missing local times are rejected with an explanatory field error.
- Preserve the mint frame, typography, semantic table and responsive stacked rows. Add a quiet work-view navigation, visible assignee/next action/deadline and focused detail form. Use real counts, visible labels, inline errors/error summary, pending/success/disabled states and existing SVGs. No new decorative dashboard cards.

## Review focus

1. Tenant/membership spoofing and membership-removal races.
2. Lost edits across status, assignment, follow-up completion and timezone changes.
3. UTC/day-boundary errors, including 23/25-hour DST days.
4. Completed/closed work incorrectly appearing overdue or reviving silently.
5. Old-data migration, backup compatibility and private test data separation.

## Tasks

- [x] **1. Test first:** Add real request/SQLite tests for schedule/assignment, validation, cross-company rejection, missing CSRF, completion/reschedule, stale writes, removal and queue filters. Add timezone/DST and migration preservation cases. Run them and verify feature failures before implementation.
- [x] **2. Backend:** Extend `db.py` migrations with lead handoff columns and workspace timezone. Add `followups.py` for validated dates, context, queue predicates and POSTs. Extend inbox queries, detail rendering and member removal with transactions/version checks. Run targeted then full tests.
- [x] **3. Interface:** Extend `inbox.html`, add reusable handoff detail section, extend `app.css`; retain current status/notes behavior. Render dates in workspace timezone, independent of browser timezone. Review desktop/tablet/phone and actual browser interactions with synthetic data only.
- [x] **4. Verify/deliver:** Fresh correctness/security review; reproduce/fix important findings. Run complete suite, Python compilation and JS/source checks. Back up real data before activation; verify all previous columns remain unchanged. Restart only the app's loopback server, package clean source ZIP, update README/verification and show the local inbox.

No Git repository exists in this generated project; source ZIPs and this plan track the release. Private backups, migration baselines and QA data remain outside published source.
