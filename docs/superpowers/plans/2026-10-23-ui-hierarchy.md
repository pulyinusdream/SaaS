# Admin and Customer visual hierarchy

User prioritised a full Admin/Customer UI rework and professional login imagery before the proposed appointment-management milestone. Implement inline in the existing Flask/Jinja/vanilla CSS app; no new business features, dependencies, auth rules, database schema or user-data changes.

## Design

Keep KJAncy's mint/forest identity, IBM Plex Sans and SVG icons. Extend the existing framed-sheet direction with calmer navigation, a clearer title/action tier, distinct work surfaces, consistent form sections and subdued secondary guidance. Admin request/calendar/team/report/settings/setup/account/workspace screens and Customer home/form/contact/account/request screens share these tokens. Customer and Admin overviews use existing real counts, clearly scoped to all requests in the active business. Conversation history precedes composing, on both sides. Keep native security disclosures, validation, pending/disabled states, source ownership and private notes intact.

Login and registration get one locally served generated architectural home image, dimensioned and compressed as WebP. Sign-in remains the primary task with an explicit Admin/Customer role choice and preserved recovery/registration routes. At phone widths the form appears first, the image story second. No invented testimonials, staff photos or performance claims.

Design research: Design Taste support draw selected framed-sheet to extend existing brand. UI/UX Pro Max returned applicable Swiss/minimal hierarchy and accessibility guidance; its landing composition/dark palette/font suggestions did not fit this existing mint work app and were not adopted. Eight actual objects: businesses, owned requests, statuses, appointments, conversations, unread counts, staff identities, private notes. Primary questions: Admin 'What needs my attention?' and Customer 'What is happening with my request?'. Existing values remain the source of truth.

## Execution and validation

- [x] Verify a failing accessible-login image/resource test before introducing the asset and layout.
- [x] Add shared hierarchy CSS and authentication photo/story component. Update role navigation, login/registration headings and main app navigation groups without changing form contracts.
- [x] Add truthful overview strips, improve list/detail/form hierarchy, and place conversation history ahead of reply/follow-up composition. Apply consistent styles across secondary routes.
- [x] Run full integration suite, compilation/dependency/JS checks and scoped app lint. Request independent read-only markup/security/form-contract review against pre-hierarchy-ui-source.zip.
- [x] Use an isolated data/cookie fixture to check both logins, customer requests/form/conversation/contact/account, and Admin inbox/detail/calendar/team/reports/business/setup/account/workspace screens. Verify desktop/phone and representative 320px/tablet widths, focus/mobile menu and no overflow.
- [x] Back up and hash live rows, restart only the owned process, verify health and updated pages without losing user drafts or creating live test records. Refresh docs/source archive and close temporary QA tab. Fixture server shutdown is not confirmed because its original exec handle was lost.

