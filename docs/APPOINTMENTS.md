# Appointment scheduling implementation plan

> **For agentic workers:** Execute inline with executing-plans and test-driven-development. The user approved the scheduling/calendar/reschedule/cancel milestone. Continue within that scope without another approval round.

**Goal:** Save actual appointments against leads and give each business a usable daily/weekly calendar.

**Architecture:** Extend Flask/SQLite/Jinja, existing company-bound CSRF, shared lead versions and workspace timezone. Add an appointments table, transactional scheduling service/routes, calendar read views and dedicated appointment editor. No new dependency, calendar provider, SMTP or public deployment.

**Spec:** Accepted conversation scope: date/start/duration, assigned teammate, overlap warnings, daily/weekly calendar, reschedule/cancel history and consistent lead status. This document records the routine implementation choices.

## Global constraints and behavior

- One active appointment per lead. Appointment assignment is separate from lead/follow-up responsibility. Both owners and dispatchers can schedule within their existing workspace permissions.
- Scheduling/rescheduling atomically marks the lead Appointment booked. Cancellation requires a reason and returns a booked lead to Contacted. Closing a lead cancels its active appointment with a recorded reason. Moving an active appointment's lead to New/Contacted requires cancellation first. Existing legacy booked statuses are preserved without inventing dates. Closed leads must be reopened before scheduling.
- Start is entered/displayed in the shared workspace timezone and stored as UTC. Duration is elapsed time, 15–480 minutes in 15-minute increments. Newly entered DST gaps/repeated times fail clearly; unchanged valid existing instants preserve their offset/fold when editing. A changed workspace timezone requires form reload.
- All writes lock, recheck acting membership, scope lead/appointment/member IDs to the current company and check lead.version before any side effect. Appointment mutations and member removal increment that version. Duplicate/stale saves cannot overwrite or create two active appointments.
- Overlap means same teammate in this workspace, start before another end and end after another start. Touching boundaries are allowed. No external/company-crossing availability is claimed. An overlap first returns a warning without writing. Scheduling anyway requires a checkbox and a ten-minute signed acknowledgement bound to the exact slot, workspace, lead and current conflicts. Changes to conflicts invalidate acknowledgement.
- Cancelling retains the appointment and activity. Dispatcher removal unassigns active appointments, records activity and invalidates affected lead forms; it does not silently cancel customer work. Calendar can show unassigned or cancelled records.
- Day/week windows and navigation use workspace-local dates, including 23/25-hour days and appointments crossing midnight. Weeks begin Monday. Query windows are paginated at 50 appointments with true totals; empty days on a partial page are labelled honestly. Malformed/out-of-range dates, views and foreign assignee filters fail safely.
- Calendar follows the current mint framed sheet, self-hosted IBM Plex Sans and SVG icons. A seven-column week becomes a vertical agenda on phones, without horizontal scrolling. Each day has a heading, real count and explicit empty state. No decorative metrics, invented bookings, drag-only interaction or external UI dependencies.
- A compact appointment panel on lead detail links to a dedicated labelled editor with customer context, inline errors/focused summary, conflict confirmation and pending/success/disabled states. Existing notes/follow-up forms retain explicit destinations and behavior.

## Review focus

1. Cross-company IDs, revoked actors and removal/scheduling races.
2. Conflicts changing after warnings, concurrent bookings and duplicate POSTs.
3. Stale cancellation/lead closure causing partial state changes.
4. DST, midnight/week boundaries, duration and pagination truthfulness.
5. Legacy booked statuses, schema upgrade and backup/restore retention.

## Tasks

- [x] **1. Test first:** Add integration tests for actual appointment persistence/status, reschedule/cancel, overlap/acknowledgement, tenant and CSRF boundaries, stale/revoked writes, removal, timezone/DST, calendar windows/pagination and backup retention. Run and observe missing-feature failures.
- [x] **2. Backend:** Add schema/indexes in `schema.sql`, scheduling in `appointments.py`, read views in `calendar_views.py`, registration in `__init__.py`, and focused status/member-removal integration. Run targeted/full tests; preserve existing lead behavior and all data.
- [x] **3. Interface:** Add `calendar.html`, `appointment_edit.html`, `lead_appointment.html`, nav/calendar SVG and scoped CSS. Add the real appointment panel to lead detail, with conditional status guidance. Verify actual browser flows on synthetic data and desktop/tablet/phone, including 320px.
- [x] **4. Review and deliver:** Fresh read-only correctness/security review; reproduce/fix important findings. Run complete tests/compilation/JS/lint. Create a private pre-upgrade backup and fresh baseline of original columns, activate locally and compare. Update README/verification, package clean source and show the actual calendar. No Git repository exists; use the source ZIP and private execution ledger.
