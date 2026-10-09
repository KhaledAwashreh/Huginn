## 1. Read-only match query model

- [x] 1.1 Add the stable management `MatchStatus` value, separate application read models, `MatchesQuery` protocol, focused request/response types, strict persistence row models, and four application services; verify service tests cover owner scoping, not-found behavior, and pagination boundaries without crossing management layer boundaries.
- [x] 1.2 Implement `PostgresMatchesQuery` parameterized reads for owner matches, owned detail, owned-match signals, owner-wide `has_matches`, active-strategy existence, and the latest owner run projection; verify disposable-PostgreSQL integration covers status filtering, stable newest-first order, <=100 pagination, identical cross-owner/nonexistent 404 results, signal ordering, read-only behavior, current Gold fields, and owner-wide existence independent of filter/page.
- [x] 1.3 Map owner-wide match existence and the latest managed run result into the overview while exposing counts only for `succeeded` and treating pending, running, stale, failed, unknown, or missing owner outcomes as unknown; verify the overview state matrix includes no active strategy, no recorded managed run, successful zero-new-match run, existing matches, and stale/incomplete results.

## 2. Authenticated management API

- [x] 2.1 Add the four authenticated GET routes, strict status/pagination validation, explicit response mapping, private response headers, and management composition wiring; verify router tests cover authentication, success/error `Cache-Control: no-store` and `Vary: Cookie`, no company-ID lookup, and correct response contracts.
- [x] 2.2 Regenerate the foundation-owned OpenAPI JSON and TypeScript declarations with the offline exporter; verify the API type-drift check passes and the management app starts without requiring frontend build artifacts.

## 3. Matches browser workspace

- [x] 3.1 Add feature-owned API adapters and session-scoped Vue Query composables for list, detail, signals, and overview; verify query tests cover status/page reset behavior, identity cache clearing, and no automatic retry for 401/403/404/422.
- [x] 3.2 Add `/matches` and `/matches/:id`, navigation, accessible list/detail/current-context components, independent signal paging, and slice-aware empty-state copy; verify component tests cover overall empty versus filtered-empty versus out-of-range page with existing matches, clear-filter/first-page actions, loading/error states, status/context labels, and existing-match precedence.
- [x] 3.3 Add strict company-domain and signal-source URL validation and use only safe HTTP(S) external links; verify URL tests reject unsafe schemes, protocol-relative values, credentials, nested/malformed values, and unsafe hostnames.

## 4. Integration and handoff

- [x] 4.1 Add an authenticated browser flow for list, filtering, detail, signals, and owner isolation; verify it renders current company/signal data as context without presenting a qualification rationale or write actions.
- [x] 4.2 Run frontend API schema/type, lint, format, unit/component, build, and browser checks; Python 3.14 compilation, Ruff, and the full live-PostgreSQL 16 pytest suite; strict OpenSpec validation, exact file/type inventory and dependency review, and a fresh Sol high review; verify no tests modify shared database state and document any environmental check that cannot run.
