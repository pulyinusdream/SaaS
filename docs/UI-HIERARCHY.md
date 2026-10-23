# Admin and Customer visual hierarchy

The mint/forest identity now uses a shared white work surface, restrained navigation, consistent headings, and clearly ranked actions across Admin and Customer pages. IBM Plex Sans, existing SVG icons, server validation, and native controls remain in use. No framework, runtime dependency, database migration, or permission change was introduced.

- Admin separates Daily work from Manage business. Customer separates Your services from Your account. The active destination is visible without competing with primary page actions.
- Requests start with an actual, clearly scoped overview. Customer Booked requests counts request statuses, not calendar appointments. Unread counts remain personal to each account.
- Inbox tables become request cards at narrower widths. Calendar weeks become an agenda when columns would be too narrow. Customer cards prioritize service, status, location, and follow-up.
- Detail pages distinguish primary content from supporting controls. Both conversations show history before composition, retain sender roles and unread state, and keep internal notes private.
- Forms, reports, team access, setup, business settings, workspace selection, and personal account sections share spacing, typography, focus, disabled, error, and success treatments. Existing actions and field contracts remain intact.
- Admin and Customer sign-in have an explicit role selector, one role-specific H1, and a locally served architectural image. Registration shares the image treatment. On phones the form precedes the image.

The decorative home-entry image was generated for this project, compressed to WebP (1122 by 1402 pixels, 249422 bytes), and is served from `kjancy/static/images/home-entry.webp`. It depicts a fictional mint entryway and makes no claim to show a real customer property. Dimensions reserve its space and an empty alt attribute avoids announcing decorative content.

Keyboard focus, existing error-summary behavior, native disclosures, mobile menu controls, pending form states, CSRF fields, role boundaries, and request ownership are preserved. Reduced-motion preferences are respected. See the latest VERIFICATION entry for measured checks and limits.
