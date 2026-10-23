# Website to inbox connection

Goal: the existing mint marketing site's walkthrough form saves a real, correctly routed lead. The user approved this milestone and asked to implement it.

Approach: serve a connected copy of the existing marketing site from the same Flask origin, at `/website/<workspace-public-id>/`. This keeps CSRF and origin protections intact, uses the established public workspace token, and avoids frontend secrets or a cross-origin API. A separate API would add CORS and deployment configuration without improving this local milestone. Direct static files retain the existing explicit email-draft fallback.

The connected form preserves name, business, email, trade, package interest and message. A walkthrough is labelled separately from a household service inquiry; it never invents a service address. Additive schema migration preserves existing users, leads and sessions. Server validation, a honeypot, rate limits and a signed expiring submission token protect writes. Replaying a successful submission creates no duplicate. Success appears only after database commit. No email or calendar confirmation is claimed.

The public connected URL includes its recipient's workspace identity. The inbox offers the workspace-specific website link. Privacy copy explains storage in that workspace, the necessary session cookie and the local hosting scope. Keep the existing mint composition, type, assets, service pages, chatbot and package selection. No new dependency or redesign.

Implementation plan (inline execution under the user's authorization):

- [x] Add failing integration tests for connected navigation, exact field preservation, recipient isolation, invalid values, CSRF, honeypot, replay, schema upgrade and missing assets.
- [x] Add transactional schema upgrade, validated walkthrough creation and same-origin marketing routes. Keep service forms and tenant boundaries intact.
- [x] Add matching connected form states, privacy copy, lead detail and inbox labels/search; retain static fallback.
- [x] Run the full app and website checks, a fresh review, and browser submission/receipt/inbox verification at desktop and phone sizes using isolated data.
- [x] Restart the local app without changing stored accounts/leads, open the connected website, save screenshots and refresh the source package.

Review focus: posted workspace IDs cannot change routing; old accounts/leads survive migration; forged or replayed writes cannot duplicate or cross tenants; validation preserves entered text without HTML injection; asset paths cannot escape the published site directory.

Verification ledger: no Git repository is present. Source snapshots and isolated test data replace worktree/commit steps. Browser QA must not submit fictional leads into the user's real workspace.

Completed: 30 app tests, 13 guide tests, source checks, fresh review and browser walkthrough flow. Real stored rows verified unchanged after migration.
