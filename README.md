# KJAncy Workspace

A working local release of KJAncy's SaaS foundation: business accounts, company-isolated lead inboxes, a separate customer portal, dispatcher invitations and a shared follow-up workflow. It uses real SQLite persistence, not browser storage or simulated dashboard data.

## Start

With Python 3.11 or newer installed, double-click **Start-KJAncy.cmd**, or run:

```powershell
python launcher.py
```

First setup creates an isolated `.venv` and installs the pinned packages from PyPI. Internet is needed for that setup. Subsequent launches use the installed environment. Then open **http://127.0.0.1:4200**. Keep the server running while using the app. Stop it with Ctrl+C.

Alternative manual setup:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

If Windows cannot write its normal temporary directory, set TEMP and TMP to a writable folder before manual setup; the included launcher already does this for its own setup process. `python launcher.py --port 4202` chooses another port.

## Try the milestone

1. Create a workspace with a business name, your email and a password of at least 12 characters.
2. In Business settings, copy the customer registration link. In a separate signed-out session, create a customer account and send a service request. Refresh the Admin inbox to see the saved request. The existing public form also accepts guests.
3. Open the lead, update its status and add internal notes. The saved activity appears below its contact details.
4. Use search and the status tabs to work through inquiries.
5. In Team access, create a dispatcher invitation. Copy the link and give it to the intended person yourself. No invitation email is sent. The invited email must match the signed-in account, and the token expires after 24 hours and is accepted once.
6. Owners can revoke pending invites and remove dispatcher access. Dispatchers can manage leads but cannot manage membership.
7. A person assigned to multiple companies can change the active workspace under Your workspaces. Access is checked against membership on every request.

Statuses are **New**, **Contacted**, **Appointment booked**, and **Closed**. A booked status records the team's own confirmation; it does not reserve an external calendar slot or automatically notify a customer. Inquiry submission saves a request and never claims an appointment is confirmed.

The connected public website has a new mint/forest editorial design, natural-color photography and shared styling across its service and privacy pages. Its walkthrough form still saves to the linked business inbox. See [Public website design](docs/PUBLIC-WEBSITE-DESIGN.md) for image credits and design notes.

## Customer and Admin conversations

In My requests, choose **Follow up** to send a message and read business replies. In the matching Admin business, open the **customer message** or unread link, then use **Reply to customer**. Both sides share the conversation; Internal notes stay private. Unread badges are personal to each account. Use **Mark displayed messages as read** after reviewing a page, and refresh to see new messages. No email notification is sent. See [Request conversations](docs/CUSTOMER-MESSAGES.md).

## Using the simpler interface

The latest visual rework gives both portals clearer title/action hierarchy, consistent form sections, scoped request summaries, readable conversations, and responsive request cards. Admin and Customer login/registration now include a locally served mint architectural image, with the sign-in form first on phones. See [UI hierarchy](docs/UI-HIERARCHY.md) for design details and the latest verification entry for actual checks.

Customer navigation is **My requests**, **New request**, **Contact details**, and **My account**. New request sends a service inquiry; Contact details saves the address/phone used to prefill it. My requests has a labelled status filter and a Refresh status link. Older documentation may call these Customer form, Get started and Account settings; their URLs and account permissions are unchanged.

Admin navigation groups **Customer requests** and **Calendar** under Daily work, with Team, Reports, Business settings, Switch business and My account below. Customer requests combines search, status and work-view filters in one form. Choose Apply filters to update the list; Clear filters resets it. Business links/timezone settings are available under the expandable section below the list. Add a lead still records an inquiry received by staff.

In **My account**, Profile opens first. Expand Password or Signed-in browsers when needed. Native expanders work without JavaScript. Validation opens the relevant section, and existing password/session links still work. Changing a password still ends every session; signing out other sessions still requires the current password. The new layout does not change account security.

On an Admin request, customer details, the appointment and Status and notes remain easy to find. Assignment/follow-up editing and activity are expandable; pending work and validation errors open the follow-up section automatically. All existing scheduling, notes, assignments, reporting, team and business-setting functions remain available. Mint colors, larger readable controls, visible Sign out and a consistent phone menu apply across both roles. See the latest VERIFICATION.md entry for actual checks and limits.

## Customer side

Customers sign in at **http://127.0.0.1:4200/customer/login**. New registration starts from the specific business's link, available to its owner in **Business settings**. Each customer account belongs to one business. The email address must be unique across customer and staff accounts.

- **Contact details** saves a phone number and usual service address. These defaults prefill subsequent requests; each request may use another address without changing the defaults.
- **New request** submits a service request to that business. The server uses the signed-in account's name/email and checks the current service list. Repeated submission of the same valid form returns the existing request.
- **My requests** shows only that customer's requests, current statuses and saved appointment dates/state. Refresh to see Admin updates. Guest requests are not claimed automatically by matching email.
- **My account** provides the existing profile, password and session controls, with customer navigation. Verification/recovery use local email preview until SMTP is configured.

Customers cannot open Admin pages, other customers' requests, internal notes, staff activity or reports. Admin continues managing leads, appointments, assignments, team access, reports and business settings. **Get started** and **Customer form** have moved out of Admin navigation. The owner's checklist remains under **Business settings → Business setup**. The connected marketing website remains available from the inbox.

Admin and Customer have separate entry points: **/login** accepts staff accounts and **/customer/login** accepts customer accounts. Correct credentials entered in the wrong portal are rejected without creating a session. A signed-in account opening the other role's sign-in/registration sees an explicit account-boundary page with **Continue** or **Sign out and switch**. It never silently changes roles. Both roles still use one account session per browser profile; use separate profiles for simultaneous testing.

### Admin and Customer functions

| Admin / business staff | Customer |
| --- | --- |
| Manage the lead inbox, internal follow-ups and appointments | Submit a service request and view only their own requests/status |
| Manage team access; owners configure business settings, setup and reports | Save personal contact defaults under Get started |
| Record received phone/email inquiries with Add a lead | Use Customer form with their account identity and linked business |
| Preview guest form fields in read-only mode | Own-business guest links lead to the authenticated Customer form |

Personal profile, password, sessions and email verification belong to each individual account and intentionally remain available to both roles. Customer requests cannot access business administration. Signed-in accounts cannot submit the guest service form; anonymous guest submission remains supported. Admin's form preview contains disabled fields and no submission action. Customer links for another business are denied instead of creating an untracked guest inquiry.

### Local sample customer

The requested sample account is **sample.customer@kjancy.test**, in **Sample Customer Workspace**, with one clearly fictional HVAC request. Its generated password is handed off in a private file outside the app; it is never a hardcoded default or part of the source ZIP. The chosen existing owner can manage this separate sample business under **Your workspaces**. No access to existing business data is granted to the customer.

For a fresh local installation, explicitly create the sample after registering an owner:

```powershell
.venv\Scripts\python.exe create_sample_customer.py --owner-email YOUR_EXISTING_OWNER_EMAIL --credentials C:\PRIVATE_FOLDER\sample-customer-credentials.json
```

Use an existing private folder outside the app source and a new filename. The command refuses existing sample accounts/workspaces or credential files, and refuses a production HTTPS/SMTP configuration. It never runs at startup, overwrites a password or sends email. The sample remains unverified; local preview permits access honestly, while strict SMTP mode requires verification. See `docs/CUSTOMER-PORTAL.md` and the latest `VERIFICATION.md` entry for scope and actual checks.

## Assignments and daily follow-ups

Open a lead to choose its **Assigned teammate**, **Next action**, and **Due date and time**. Both owners and dispatchers can manage handoffs within their existing workspace access. Assignment is responsibility, not a new visibility restriction. New and migrated leads start unassigned, without invented deadlines.

The inbox has **All leads**, **My leads**, **Unassigned**, **Due today**, and **Overdue** views. Work-view counts cover the workspace; status counts cover the selected work view. Search and status filters combine with the work view, and pagination retains them. Refresh to see another teammate's changes or a deadline that has just passed. These are saved in-app reminders, with no background popup, email, SMS or calendar delivery.

The default workspace timezone is **UTC**, shown beside the filters and due input. An owner can choose **Change timezone** in the inbox; the setting is shared by the team. Existing deadlines retain their actual instant when the displayed timezone changes. Due today means the full local calendar day, including an overdue task from earlier that day; Overdue means strictly before now. These two views can overlap. Completed follow-ups and closed leads are excluded. Closing pauses a pending reminder; reopening resumes it.

Choose **Complete follow-up** and describe the outcome to finish the current action. Change its action or due time and save to schedule the next one. Leave both fields blank to clear the current follow-up. Saving an assignment alone does not revive completed work. Past times are accepted and appear overdue. A newly entered time skipped or repeated by a daylight-saving clock change is rejected rather than silently shifted; an unchanged existing deadline retains its original instant even during a repeated hour.

Assignments, scheduling, completion outcomes and removal-related unassignment appear in the lead's activity. Removing a dispatcher automatically unassigns their leads and rejects stale edits. All handoff and status forms share the lead's version, so concurrent changes require a reload rather than overwriting a teammate's work.

## Email verification and recovery

Email verification, resend and password recovery are implemented. This delivery uses **local email preview** because no SMTP service is configured; no email is sent. In the workspace choose **Email verification**, or choose **Forgot your password?** from sign-in. Then use `Read-EmailPreview.cmd` to read the privately saved local message and open its link yourself. Preview messages contain account-access links: never share them or put them in a public folder.

Verification links expire in 24 hours and reset links in 30 minutes. Opening a link does not consume it; confirmation is an explicit CSRF-protected action. Reset validation errors preserve the link. A successful password reset revokes all sessions and outstanding account links, then requires sign-in. Old accounts remain unverified until confirmed. The local preview keeps workspace access available; SMTP mode enforces verification before access.

See **SMTP-SETUP.md** for the local steps, security boundaries, SMTP environment configuration, queue operation and remaining deployment requirements. SMTP uses certificate-validated STARTTLS or SSL and does not fall back to plaintext. Delivery is queued outside the request path; no provider account or credential is configured, and real inbox delivery has not been tested.

## Connected marketing website

In the inbox, choose **Open website** or **Copy website link**. Each link includes that workspace's public routing token. The connected marketing site is served by this app from `marketing/`, with the existing mint design, local fonts/images, service pages and preset website guide.

The walkthrough form submits directly to the workspace inbox. It preserves the visitor's name, business name, email, trade, package interest and message. The inbox labels it **Walkthrough**; the detail page shows its source and package. It does not invent a household service address. Search also includes business names and package interest.

The form saves without JavaScript. Browser feedback adds required-field checks and a sending state; server validation remains authoritative. A signed two-hour submission token and a unique database key prevent repeated clicks or concurrent POSTs from creating duplicate leads. Success follows a committed save and never claims an automatic email or calendar confirmation. Refresh an inbox opened in another tab to see new inquiries.

Use the app-served website URL for direct inbox delivery. The older standalone `kjancy-website/dist/index.html` version retains its explicit email-draft fallback. No credential or private workspace ID is embedded in the marketing source. The public URL controls recipient routing on the server.

The upgrade adds four lead metadata columns and an index in a transaction; existing accounts, leads and sessions are preserved. Runtime data remains outside the source. Connected privacy copy explains actual local storage and the necessary session cookie. Editing the connected website's design assets happens in this app's `marketing/` folder; the original static website remains a separate snapshot.

## Appointments and calendar

Open a lead and choose **Schedule appointment**. Select the attending teammate, start time and duration (15 to 480 minutes, in 15-minute increments). Times use the shared workspace timezone configured in the inbox. Appointment assignment is separate from follow-up ownership. Saving reserves a workspace calendar entry and marks the lead **Appointment booked**; contact the customer to confirm.

**Calendar** provides day/week views, date navigation, teammate/My appointments/Unassigned filters, and optional cancelled history. Weeks start Monday; overnight appointments appear on both days with continuation labels. Large periods are paginated at 50 appointments, with the true total and page range shown. Refresh to see another teammate's changes.

Overlapping work for the same teammate in this workspace first produces a warning without saving. Choose another time/person, or explicitly acknowledge the listed overlaps and save again within ten minutes. Changed slots or conflicting bookings require a fresh review. Appointments in other workspaces and external calendars are not checked. Touching start/end boundaries are allowed.

Use **Reschedule or cancel** on the lead to change the appointment. Cancellation requires a reason, retains history and returns a booked lead to Contacted. Closing the lead cancels its active appointment with a recorded reason. Cancel first before moving an active booking back to New/Contacted. Reopen a closed lead before scheduling. Removing a dispatcher leaves their active appointments unassigned for reassignment, preserving the customer reservation.

Only one active appointment per lead is supported. Old leads marked Appointment booked retain their status but have no calendar entry until an actual date is saved. Newly entered nonexistent or ambiguous daylight-saving times are rejected; an existing unchanged repeated-hour time preserves its original instant. Changed workspace timezones and stale edits require reloading before saving. Calendar and lead writes share optimistic version checks and transactional membership checks.

There are no automatic customer confirmations, calendar invitations, Google/Outlook synchronization, SMS or push notifications. The new table/indexes are additive; existing customer/account values are preserved. See `docs/APPOINTMENTS.md` and the latest `VERIFICATION.md` entry for scope and executed checks.

## Business settings and guided setup

Workspace owners can open **Business settings** to save the business name, public contact email/phone, services, service areas and shared timezone. At least one public contact is required. Phone numbers need 7–15 main digits and may include an `x` extension of 1–8 digits. These details are public on the customer service form; they do not replace the owner's private sign-in email or configure SMTP.

List 1–20 services and 1–20 service areas, one per line. Service names allow up to 60 characters; areas allow up to 100. Names are unique without regard to case. New customer inquiries and manually added leads use the workspace's current service list. A choice removed while a form was open is rejected clearly on submit. Previously saved leads keep their original service/location. Areas are guidance, not an automatic geographic restriction: customers can still enter an address for the team to review. The marketing walkthrough's trade choices remain separate because they describe the business requesting KJAncy's support.

Defaults preserve the original six service choices with blank contact details and service areas; they do not pretend setup is complete. Saving settings requires the current settings version. A newer settings or inbox timezone change rejects an old settings form with a reload action. Existing follow-up and appointment instants never move when the timezone changes. Dispatchers cannot open/edit settings or mark owner setup steps.

**Business setup**, reached through Business settings, tracks three required steps: saved business configuration, the owner's explicit acknowledgement that the customer form link was shared, and an actual saved guest-form, customer-portal or connected-website inquiry. Team invitation is optional; pending invitations are not presented as active teammates. Copying or opening a form does not claim delivery. Owners can clear the sharing acknowledgement. The checklist remains available after completion; Admin's inbox no longer carries the setup prompt.

New requests use server-controlled `customer_form` or `manual` source metadata; submitted source/company values cannot change routing or checklist progress. Original `service` records use their existing inquiry activity to recognize legacy customer forms without rewriting records. Historical actor display-name collisions cannot be resolved conclusively from that older metadata. Setup progress is a local workflow aid, not delivery tracking or a production-readiness certification. Sharing loopback links still works only on this computer until hosting is configured.

## Reports and CSV

Owners can open **Reports** for lead status summaries or scheduled/cancelled appointments. Filter by inclusive dates in the shared workspace timezone, service and responsible/attending teammate. The default is the last 30 local dates; ranges allow up to 366 dates between 2000 and 2100. Removed services and referenced former teammates remain available as historical filters. Dispatchers cannot view or export reports.

Lead dates mean when an inquiry was received. Status and assignment values are current; Closed does not imply a won sale, and a legacy booked status may have no appointment. Appointment dates mean saved slots overlapping the range, regardless of when the lead arrived. Reschedules use the latest slot, and cancelled slots retain their current state. These summaries do not reconstruct past conversions or cancellation events.

Each page shows up to 25 rows. **Export CSV** downloads all filtered rows, including other pages, with a maximum of 10,000 rows. Narrow larger reports; exports are never silently truncated. An empty report exports headers only. Downloads use UTF-8 with BOM, quoted fields and local timestamps containing UTC offsets and the workspace timezone. Internal notes, customer messages and private account fields are excluded. Spreadsheet-sensitive text has a protective apostrophe prefix, including phone numbers beginning with `+`; import behavior can vary between spreadsheet applications.

Export links expire after 30 minutes and are bound to the displayed workspace, timezone and filters. Reopen Reports after switching workspace/timezone or when a link expires. Downloads recheck current owner access and use the latest committed data for the signed filters; they are not a frozen copy of an earlier screen. Keep downloaded customer contact details private. No email service is needed. See `docs/REPORTS.md` for the full scope and `VERIFICATION.md` for executed checks.

## Account settings and sessions

Open **Account settings** to update your display name, change your password or review active sessions. These settings belong to your personal account across all workspaces; both owners and dispatchers can manage their own account, including before email verification. Workspace access still follows the existing verification and membership rules. Your sign-in email is read-only here; the verification link opens the existing email flow.

Display names allow 1–100 characters without control/format characters. A stale form is rejected with a reload action rather than overwriting a newer profile. Existing recorded activity keeps its original actor name; current assignment displays use the updated name.

Changing your password requires your current password and a different, confirmed new password of 12–128 characters. Password managers and paste are supported. Success signs out **every session, including the current one**, and invalidates unused recovery/verification links. Sign in again with your new password; request a fresh account link if needed. Passwords are hashed with the existing scrypt implementation and are never echoed into returned forms. Current-password confirmation attempts are rate limited.

Active sessions show true expiry times and, for new sign-ins, creation times and an allowlisted browser/platform label. Times are in UTC. Older sessions show unavailable sign-in metadata honestly. Browser labels are client-reported hints, not verified devices, locations or live-activity indicators; tabs may share a session. The list contains only your account's unexpired sessions, with 25 per page and the current session first. No session identifiers, raw user agents or IP addresses are shown or stored as metadata.

**Sign out other sessions** requires your current password and preserves the session making the request. It cannot sign out another account's sessions. A new sign-in can create another session afterward; change your password if someone else knows it. Sensitive changes recheck the exact session and authenticated credential within the write transaction to reject stale or revoked access. No SMTP service is needed for these controls. See `docs/ACCOUNT-SECURITY.md` and `VERIFICATION.md` for scope and executed checks.

## Saved data

The default data folder is:

```text
C:\Users\vicen\Documents\Codex\kjancy-data
```

It holds `kjancy.sqlite3`, SQLite's journal files while running, and `session.key`. Data stays outside the app source and source ZIP. Do not delete that folder when updating the app. The key signs session cookies; replacing it signs existing browsers out. Use `Backup-KJAncy.cmd` or `python backup.py create` for a verified online database backup. Recovery generates a fresh signing key and revokes sessions, account links and pending invitations. Keep backups private; they contain customer records and password hashes.

Set `KJANCY_DATA_DIR` to use a different private data directory. Automated tests and browser QA use isolated databases. The app never seeds accounts at startup. This local delivery contains the explicitly requested sample customer in a separate sample workspace; all previously existing records were preserved. Runtime data and private credentials are excluded from the source ZIP, so a fresh installation starts empty unless the sample command is explicitly run.

## Deployment and backups

See **DEPLOYMENT.md** for online backup, verification, safe recovery into a new folder and hosting configuration. `serve.py --check` validates the separate HTTPS/SMTP hosting profile without starting a server or changing data. Docker/Compose templates use persistent storage and an unprivileged process. The local launcher remains unchanged. No hosting account, public site, domain or SMTP service has been configured; Docker's engine was unavailable for an image build/runtime check.

## Security boundaries

- Passwords use Werkzeug scrypt hashing. Authentication uses a signed HttpOnly, SameSite=Lax cookie plus a random session token whose digest and fixed eight-hour expiry are stored in SQLite. Logout revokes that session on the server.
- Every write requires a CSRF token signed for the current browser and company. Old forms are rejected after another tab switches workspace, preventing a customer record from landing in the wrong company.
- Lead queries, changes, searches, counts, invitations and member controls enforce the authenticated workspace membership. Submitted company IDs do not control public inquiry ownership.
- SQL uses parameters for input values; Jinja escapes visitor text; the app sets CSP, framing, no-sniff, no-referrer and no-store headers. Forms have server-side length/format checks, request size bounds and persisted rate limits.
- Invite tokens are random and stored as digests. Acceptance conditionally claims the token in the same transaction as membership creation. Only owners can create/revoke invites or remove dispatchers.
- The launcher binds Waitress to **127.0.0.1 only**, and trusted hosts are restricted to loopback. The desktop in-app browser submits an opaque `Origin: null`; the local launcher permits this only with a valid company-bound CSRF token. The app factory defaults to rejecting opaque origins. Other cross-origin form submissions remain rejected.

## Deployment scope

This is a functional local release. Customer form and invitation links are loopback URLs that work on this computer. It is not a hosted multi-device SaaS yet. SQLite data is local and is not an encrypted cloud database.

Before public hosting, configure the domain and HTTPS, secure cookies, trusted-host/proxy settings, production database and migrations, operational backups, a real SMTP service and verified sender for the implemented verification/recovery flows, delivery/abuse controls and monitoring. Keep opaque-origin compatibility disabled on a public deployment. Real email, SMS/calling, external calendars, AI models and subscription billing are intentionally unconfigured in this milestone. No API credentials are embedded. The marketing website remains a separate deliverable.

## Development and checks

Stack: Flask, Werkzeug, Jinja, SQLite, Waitress; semantic server-rendered HTML, self-hosted IBM Plex Sans, CSS and progressive JavaScript. Forms and links work without JavaScript; JavaScript adds clipboard feedback, local time formatting, pending states and the mobile navigation drawer.

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q kjancy run.py launcher.py
node --check kjancy/static/app.js
```

No TypeScript or JavaScript bundler is used. See `docs/PLAN.md` for scope and `VERIFICATION.md` for executed checks, the fresh security review and remaining limitations.

Design: Taste Skill **Framed sheet**, seed **716491800**, with a mint L-frame and a white work surface. IBM Plex Sans is self-hosted under its SIL Open Font License (`kjancy/static/fonts/OFL.txt`). No external fonts, tracking scripts or image requests are needed at runtime. Icons are consistent inline SVGs. Test previews show fictional QA data, not customer proof.
