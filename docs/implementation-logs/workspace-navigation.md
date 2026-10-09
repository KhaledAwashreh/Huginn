# Workspace navigation redesign

Approved scope: grouped sidebar and focused Administration workspace using installed PrimeVue 4 components. Existing routes, forms, API contracts, database, job controls and user data are preserved. No dependency downloads or publication.

- [x] Group workspace navigation and provide a responsive PrimeVue Drawer.
- [x] Add an Administration landing page and route-backed PrimeVue tabs while retaining deep links.
- [x] Verify admin visibility, deep links, active sections, keyboard access and narrow layout.
- [x] Run frontend schema, types, lint, format, unit, build and browser gates.
- [x] Resolve fresh-context Sol high review.

Implementation uses PrimeVue Menu/Drawer/Button for navigation and Card/Tabs for administration. Existing collection/matchmaking components remain responsible for triggers, paging, progress and uncertain receipts. No backend or PostgreSQL changes are required.

Verification completed 2026-10-09:

- Frontend API schema/types, TypeScript, ESLint, Prettier, all 166 unit tests and production build passed on final source.
- Full installed-Chromium browser suite: 17 passed against a separate disposable PostgreSQL 16 fixture. Final focused navigation rerun passed after the last aborted-navigation focus and active-style adjustments.
- One new browser scenario covers grouped navigation, admin-only entry, route-backed tab keyboard activation/focus, preserved deep-link selection after reload, 320px Drawer, accessibility checks and canceled mobile dirty drafts. Existing configuration label selector updated for Account & security.
- Wide and narrow screenshots inspected. Collection tables now expose named keyboard-focusable scrolling regions because the sidebar reduces content width.
- Strict OpenSpec validation: all seven local changes passed. Git diff whitespace check passed.
- Fresh-context Sol high review resolved all findings: preserve tab focus, wait for successful navigation before closing the Drawer, and skip heading focus after canceled route guards. No remaining actionable findings.
- Existing preview serves updated sidebar at http://127.0.0.1:4173; API8000 readiness remains HTTP200. No real-data queries or job triggers were needed for verification; browser fixtures were disposable.

No Python/backend/schema changes or dependency downloads. Existing production-bundle size advisory remains; no commits, push, PR or Jira updates. User review is pending.

User reviewed the running UI and authorized committing the integrated feature on 2026-10-09. Push remains reserved for the user.
