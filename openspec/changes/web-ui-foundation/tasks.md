## 1. Implementation base and frontend setup

- [x] 1.1 Select a dedicated feature worktree from the actual layered-management base or its merged successor and record baseline/source comparison; verify unrelated primary files and existing worktrees are unchanged.
- [x] 1.2 Scaffold `frontend/` with Vue 3/TypeScript/Vite, Router, PrimeVue and Vue Query using the exact inventory and authoritative Node 24/npm/package-lock contract; verify npm ci, strict vue-tsc/tooling checks, ESLint flat config/Prettier and production build succeed.
- [x] 1.3 Add Vitest/Vue Test Utils/jsdom and Playwright/axe with the named scripts; integrate CI and conditional existing hooks while preserving API-only operation; verify real component/browser interactions and required-check missing-prerequisite failures.
- [x] 1.4 Add offline deterministic app.openapi() export and locked openapi-typescript generation with both committed outputs and temporary comparison gate; verify no DB/server/network dependency, generated output matches schemas, and api:check fails on deliberate schema/type mismatch without modifying committed files.

## 2. Session bootstrap and typed transport

- [x] 2.1 Add separate session-read application request/response/service and API response file and existing session router; verify valid-session bootstrap returns IDs/proof/expiry and missing/expired/revoked/disabled sessions return generic 401 with no-store headers.
- [x] 2.2 Implement stable purpose-separated per-session CSRF derivation, new-login storage and atomic legacy digest transition; verify two simultaneous bootstraps remain compatible and no opaque credential is returned/logged.
- [x] 2.3 Add shared same-origin browser auth-mutation guard to existing login while retaining trusted nonbrowser clients; verify cross-origin browser login is forbidden and same-origin login works.
- [x] 2.4 Implement typed cookie/CSRF fetch client,204 decoding and native 422/error-envelope normalization; verify field paths,401/403/409/429 handling and disabled unsafe automatic retries with contract tests.
- [x] 2.5 Implement session bootstrap, login/logout, validated local return path and account-scoped query cache clearing; verify reload, logout, account switch and expiry never reuse another user's cached data.

## 3. Shared UX and application delivery

- [x] 3.1 Add app shell/router/tab extension points, PrimeVue theme tokens and `frontend/DESIGN.md`; verify navigation and shared form/status states against the documented visual contract at wide/narrow viewports.
- [x] 3.2 Add reusable loading/empty/error/field feedback and dirty-draft navigation primitives; verify WCAG 2.2 AA target with axe plus manual keyboard/focus/reflow/contrast/reduced-motion evidence and background refetch preserving unsaved inputs.
- [x] 3.3 Add development API proxy and optional production static-assets mount with bounded SPA fallback; verify deep links work while unknown API/assets return 404 and API/docs/health routes remain intact without frontend build artifacts.

## 4. Integration and handoff

- [x] 4.1 Add session/API/browser integration against a uniquely named disposable PostgreSQL 16 database; verify multi-tab CSRF, legacy migration transition, expiry and login-to-reload mutation end to end without resetting shared data.
- [x] 4.2 Record runtime/build/deployment/session ADR and runbook, including API-only startup and rollback; verify documented commands against the chosen worktree and keep implementation log/checklists current.
- [x] 4.3 Run frontend type/lint/build/interaction checks, Python 3.14 compilation, Ruff check/format, full pytest including live PostgreSQL 16 tests, and strict OpenSpec validation and exact file/type inventory/dependency review against the chosen implementation base; resolve fresh Sol high review findings before any separately authorized commit/push.
