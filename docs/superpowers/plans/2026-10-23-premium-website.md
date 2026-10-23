# Premium public website redesign

**Goal:** Rework KJAncy's public website into a polished mint/forest editorial service site while preserving its connected walkthrough, chatbot, pricing and service-page routes.

**Architecture:** Buildless HTML/CSS/vanilla JS served by the existing Flask website blueprint. Work in an isolated marketing copy, validate with separate data/cookies, then copy verified public assets into the existing marketing folder. No auth, schema or business-rule changes. No deployment.

**Design decisions:** User delegates noncritical design choices. Retain mint/forest, introduce locally served IBM Plex Sans from the existing app beside Source Serif 4, and use natural-color trade photographs plus one newly generated headset desk still life. The short headline incorporates the support photograph as the visual handoff. Restrained shapes, generous spacing and varied section composition supply the premium treatment; avoid proof claims, decorative badges and generic icon cards. Existing packages remain $997/$1997 monthly plus $500 setup, with agreed coverage hours. Keep service information complete.

**Approaches considered:** An editorial image-and-type composition best fits the trade/support relationship. A dense board would resemble app UI; a type-only cover would underserve the requested imagery. Design Taste direction sentence-as-layout seed50067295 guides the headline/media relationship; brand typography overrides the dealt font. The second deal returned the prior site's editorial-report geometry, so no redraw was adopted. UIUX initial luxury query returned irrelevant Apple glass; the narrower home-service agency result supplied suitable flat hierarchy/CTA/accessibility guidance, with its blue/orange palette and generic icon rows rejected in favor of existing mint branding.

**Subject inventory:** KJAncy wordmark; US home-service trades; HVAC/plumbing/roofing/garage doors/electrical; online lead handoff; human dispatch; $997/$1997 packages; $500 setup; agreed hours; existing private workspace connection; no automatic booking promise; local preset guide; publicly credited trade photography. Idea: the headset bridges Good work and Great backup. Live interaction: existing package selector and clearly labelled handoff example.

**Argument/copy deck:** Hero: explain websites/lead follow-up/human dispatch and invite a walkthrough. Services: show the three handoffs with service-specific photography and actual detail pages. Process: explain inquiry, human follow-up, agreed appointment with an interactive labelled example. Packages: choose coverage, compare exact inclusions and limits. About: connect trade work to practical support without invented team portraits/testimonials. FAQ: answer coverage, AI and setup questions. Contact: existing server-connected form and direct email. Footer: clear service/section/privacy/credits links.

## Execution

- [x] Build isolated public copy, generate/compress purpose-built image and preserve credits, static form replacement marker, JS selectors and original field contracts.
- [x] Recompose homepage and apply shared typography/navigation/image/form/footer design to detail and privacy pages. Preserve all prices, coverage terms, chatbot disclosure and connected states.
- [x] Run existing website integration tests against staged source, JS syntax/source lint, static route/asset/anchor checks; inspect desktop1440/tablet768/phone390 and320. Verify nav, package selection, demo, guide and form validation/delivery using isolated data only.
- [x] Independent final review against source ZIP for contracts, links, claims and accessibility regressions. Fix consequential issues.
- [x] Back up/hash real data, activate public assets, verify live read-only without losing user inputs, recheck data hashes, update docs and source ZIP, reset viewport and stop owned QA process.

**Verification limits:** CUA is the supported browser path; do not run the skill's direct-browser inspector or circumvent it with another browser-control library. Record actual DOM/visual checks instead. Existing tests cover security and delivery; do not write snapshot tests merely mirroring a reversible visual edit. New behavior, if required, needs meaningful regression coverage.

