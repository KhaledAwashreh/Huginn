## Context

See [proposal.md](proposal.md) for motivation. Planning is stored in the primary checkout; the observed implementation base is `.worktrees/simple-matchmaking` at `ca2ddd9`. Primary is older and contains unrelated changes that must not be absorbed. The inspected management implementation already has layered FastAPI, synchronous psycopg, cookie sessions, and CSRF; no frontend package or session-read endpoint exists.

Observed files: `management/presentation/api/routers/sessions.py`, `dependencies/authentication.py`, `responses/authentication.py`, `errors/{shapes,handlers}.py`, `app.py`, and `docs/management-foundation.md` in that implementation worktree. Login returns only CSRF proof/expiry. The database stores token and CSRF digests. Native 422 errors use `detail`; other public errors use `error`. API CSRF failures are 403, not 419.

## Goals / Non-Goals

**Goals:** A reusable browser and API boundary supporting independent feature changes; reliable reload, isolated private query data, intentional accessible UI.

**Non-Goals:** A second Node application server, SSR/SEO, Next.js, a generic form-rendering framework, a backend restructure, or feature editors in the foundation change. Login/logout belong here; signup/recovery pages belong to the lifecycle change; password editing belongs to the user workspace.

## Decisions

### 1. Vue application and explicit feature folders

Use Vue 3 Composition API, TypeScript, Vite, Vue Router, PrimeVue with one standard theme, and TanStack Vue Query. These were selected with the user. FastAPI owns all business behavior; a browser SPA fits JSON configuration workflows without an extra server runtime. React/Angular remain viable alternatives but do not justify revisiting the agreed choice.

| Placement | Responsibility |
| --- | --- |
| `frontend/src/app/` | App composition, router, query client, session bootstrap, app shell |
| `frontend/src/api/generated/` | Generated OpenAPI transport types; no domain business rules |
| `frontend/src/api/client.ts` | Typed fetch wrapper, cookie/CSRF injection, 204/error decoding |
| `frontend/src/shared/ui/` | Page header, field/error feedback, loading/empty states, status text |
| `frontend/src/shared/theme/` | PrimeVue preset and application spacing/type tokens |
| `frontend/src/features/session/` | Login page, logout action, session queries and state |
| `frontend/src/features/account-lifecycle/` | Reserved for separate signup/verification/recovery change |
| `frontend/src/features/configuration/` | Reserved for user workspace modules |
| `frontend/src/features/pipeline/` | Reserved for administrator console |

Types are generated from the selected implementation base's OpenAPI document with a reproducible command and committed output; CI checks drift. Use local feature query/composable files, not a global store for every entity. Query keys are scoped to current Account/User. Clear the query client when session identity changes. Query errors distinguish auth, field validation, conflicts, throttling, and unavailable service.

### 2. Bootstrap and stable CSRF proof

Add `CurrentSessionResponse` separately under API responses and a narrow application session-read service/request/response in their own files. `GET /api/v1/sessions/current` authenticates through the existing dependency and returns account/user IDs, proof, and expiry with `Cache-Control: no-store` and `Vary: Cookie`. No caching or cross-origin credential access is enabled. Login is followed by bootstrap, so the existing login response need not grow identity fields.

Derive CSRF proof deterministically with HMAC-SHA256 keyed by the high-entropy raw opaque session credential and a fixed versioned CSRF context. The raw credential is available only to the server through the HttpOnly cookie and is never returned. Store only the derived proof's digest in the existing session row; login uses this derivation for newly issued sessions. On first bootstrap of a legacy session, atomically replace its old random proof digest with the stable derived proof digest. Concurrent bootstraps converge on the same proof. Existing active sessions remain valid; an older already-open page with the old proof gets existing 403 and explicit reload guidance, never an automatic mutation replay. Deterministic derivation avoids storing plaintext proof, adding a new signing secret, or rotating proof on every tab reload.

The server MUST validate same-origin browser access by normal same-origin policy, no permissive CORS, and an Origin/Fetch-Metadata guard on public auth mutations (owned by the lifecycle module; apply the same guard to existing login here). Legacy operator clients without browser-origin headers remain supported. Cookies retain secure/HttpOnly/SameSite settings; development Vite proxies `/api` to FastAPI. No tokens in localStorage/sessionStorage. API responses are the authority for expiry/disabled state.

### 3. Compact visual contract

Use a restrained operations workspace: fixed-height header with product name and account menu, top-level routable tabs on wide screens, an accessible overflow/menu on narrow screens, and one main content column. A page header names the task; primary action sits consistently at its upper end. Use the PrimeVue theme's semantic action, surface, text, border, danger, warning, and success tokens. Set a single system-sans family, 16px body, 14px table/helper text, 24px page titles, 1.5 body line height, 4px spacing rhythm, 8px control/card radius, and content width near 1120px. Use compact tables for collections and grouped forms for editors. Color is accompanied by status text. No decorative dashboard metrics or required imagery.

Document reusable design tokens and navigation in `frontend/DESIGN.md` during implementation. Verify wide/narrow layouts, focus traversal, long labels, validation and errors against rendered pages, not only component structure.

### 4. Delivery without another runtime

Build static assets in `frontend/dist`. Mount them through FastAPI after API/docs/health routes, with a narrowly scoped frontend history fallback excluding `/api`, `/docs`, `/redoc`, `/openapi.json`, `/health`, `/ready` and asset paths. Missing assets return 404. Hash-named assets get long immutable caching; index/session responses do not. Do not require a built frontend for backend tests or CLI startup. Missing frontend assets produce documented API-only operation.

### 5. Rollout dependency map

| Change | Depends on | Owns |
| --- | --- | --- |
| `web-ui-foundation` | Existing layered management | Shell, theme, login/logout, session bootstrap, API transport |
| `public-account-lifecycle` | Foundation for pages; existing management for server | Signup, required email verification, recovery, lifecycle mail |
| `user-configuration-workspace` | Foundation and existing CRUD | Personal/professional/offering/ICP/strategy editors, password change |
| `pipeline-control-and-history` | Existing management and full ELT | Roles, durable invocation worker, stage/source history APIs |
| `admin-pipeline-console` | Foundation and pipeline server module | Admin tab, trigger, per-invocation stages, history |

Implement foundation first. The lifecycle, user workspace, and pipeline server can then proceed independently; admin console follows pipeline contracts. Backend lifecycle and pipeline work can be tested before browser integration. Existing trusted owner accounts remain a valid vertical-slice test path. Do not create controls for unbuilt WIP entities: BuyerPersona, EngagementPreferences, MatchScore, MatchFeedback, Activity, evidence/contributions/occurrences/digests/resurfacing, and manual entity-review actions are deferred.

### 6. Shared implementation standards (authoritative for all five changes)

This section owns the shared tooling, language, directory, and accessibility contract. The four dependent designs reference it; feature files below extend its inventory without redefining versions or gates. Frontend folder organization and one file per named request/response/read model/entity/value object/repository/service, with related error families and constants grouped by responsibility, are adopted project conventions, not requirements imposed by Vue or Python. Existing management aggregations such as `application/services/authentication.py`, `domain/errors/errors.py`, and `persistence/row_models/resources.py` remain in place; these changes do not reorganize legacy source.

1. **Reproducible tooling:** Use supported Node 24 LTS with `frontend/.node-version` pinning the exact supported patch selected and verified at implementation. Set `engines.node` to `24.x` and `packageManager` to the exact compatible npm version, record that version in the runbook, and enforce it in CI. Commit `frontend/package-lock.json`; use `npm ci`, never an implicit latest-version install. Exact direct dependencies, including `openapi-typescript`, are resolved deliberately and saved without floating ranges. Vite's Node prerequisite must be checked when selecting its locked version. No pnpm/yarn/Bun lockfile is introduced.
2. **TypeScript:** Vue Composition API SFCs use `<script setup lang="ts">`. `tsconfig.app.json`, `tsconfig.node.json`, and `tsconfig.test.json` enable `strict`, `noUncheckedIndexedAccess`, and `exactOptionalPropertyTypes`; app aliases match Vite and tests. `vue-tsc --noEmit -p tsconfig.app.json` checks SFC/application types, and `tsc --noEmit -p tsconfig.node.json` checks tooling files; `vue-tsc --noEmit -p tsconfig.test.json` checks component/unit/browser test TypeScript and Vue imports. Test-only jsdom/Vitest globals are confined to that test project and do not leak into application/tooling compilation. Include Playwright test/config types explicitly; runners transpiling tests do not replace this check. Vite build alone is insufficient. Generated transport types stay immutable; feature drafts/mappers use narrow local types without blanket `any` or casts that hide validation failures.
3. **Lint/format:** `eslint.config.js` is flat config using ESLint, typescript-eslint, eslint-plugin-vue's Vue 3 rules, the Vue parser with TypeScript parser delegation, and eslint-config-prettier to disable conflicting formatting rules. Enforce multiword PascalCase SFC names (only `App.vue` is the Vue root exception), composables `useX`, camelCase TS functions/variables, PascalCase types, UPPER_SNAKE_CASE named constants, kebab-case feature directories, and camelCase helper module filenames. Prettier owns formatting including Vue/TS/JSON/CSS. Generated OpenAPI outputs and build/report directories are excluded from formatting/lint, but generated TS is type-checked. Avoid unrelated barrel/umbrella exports.
4. **Tests:** Vitest with Vue Test Utils and jsdom checks component behavior, form serialization, errors, session/cache boundaries, polling and cancellation. Playwright checks browser flows in Chromium against deterministic fixtures; `@axe-core/playwright` scans representative pages/states with WCAG 2.2 AA tags. Target WCAG 2.2 AA; automated scans are supplemented by manual keyboard/focus, labels/errors, zoom/reflow, contrast/status and reduced-motion checks at wide/narrow sizes. Acceptance includes visible labels/autocomplete/password-manager support and unrestricted paste for authentication (3.3.8), focus not obscured (2.4.11), targets at least 24 by 24 CSS px or documented spacing exceptions (2.5.8), normal text contrast 4.5:1 and large text/UI contrast 3:1, and reflow at 320 CSS px with usable scrolling for genuinely two-dimensional tables. Record manual criterion outcomes; passing axe is not a claim of conformance. Browser tests must use harmless executors, isolated accounts/disposable PostgreSQL 16 where live API behavior matters, and never invoke external scraping as setup.
5. **Backend:** Follow `CLAUDE.md`, actual `pyproject.toml`, and architecture/ADRs; Python 3.14+, uv/uv.lock, snake_case modules/functions, PascalCase classes, uppercase constants, modern union/container annotations, frozen dataclasses changed by replacement, `typing.Protocol` before adapters, plain pytest/TDD for implementation, parameterized synchronous psycopg and bounded `ThreadPoolExecutor` concurrency. Ruff check/format are mandatory. `BEST_PRACTICES.md` contains stale statements about Ruff installation; the adopted `CLAUDE.md` and configured source win. Pyright remains deferred and is not installed/configured by these changes.
6. **Layers:** New application request/response files and services expose `execute(Request) -> Response`; application projections live in `application/read_models`, persisted row validation only in `persistence/row_models`, entities/invariant value objects only in domain. Domain imports no application/persistence/HTTP/SMTP models. Application ports use `application/protocols` consistently with existing `matchmaking/application/protocols/clock.py`; management has no existing application-contract directory to preserve. Management persistence repository ports remain in its existing `persistence/contracts/repositories`; pipeline adopts that management convention. Preserve matchmaking's existing `persistence/repositories/protocols` paths. UoW implementations depend on and implement their Protocol; database/session/transaction contracts are reused, not duplicated per use case. No domain repository imports application projections: query ports returning projections belong in application protocols.

#### Named scripts and gates

Run npm commands from `frontend/` (root equivalent `npm --prefix frontend run <name>`). These are required package scripts and their exact behavior. Shell invocations by development agents use the repository RTK prefix (for example rtk npm --prefix frontend run check); package script command bodies remain normal npm/tool commands:

| Script | Command / behavior |
| --- | --- |
| `dev` | `vite` with same-origin `/api` development proxy |
| `typecheck` | `vue-tsc --noEmit -p tsconfig.app.json` then `tsc --noEmit -p tsconfig.node.json` then `vue-tsc --noEmit -p tsconfig.test.json` |
| `lint` | `eslint . --max-warnings 0` |
| `format:check` | `prettier . --check` honoring committed ignores |
| `format` | `prettier . --write` honoring committed ignores |
| `test:unit` | `vitest run` (Vue Test Utils/jsdom) |
| `test:e2e` | `playwright test` (includes axe scans) |
| `build` | `npm run typecheck` then `vite build` |
| `api:export` | Invoke root `uv run python scripts/export-management-openapi.py --output frontend/src/api/generated/openapi.json` from repository cwd |
| `api:generate` | `npm run api:export` then locked `openapi-typescript src/api/generated/openapi.json -o src/api/generated/schema.d.ts` |
| `api:check` | `node scripts/checkApiTypes.mjs`: export schema and generate TS into a temporary directory, compare both byte-for-byte with committed outputs, fail on drift, and clean up without rewriting committed files |
| `check` | `npm run api:check`, `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run test:unit`, `npm run build` sequentially |

The Python exporter invokes the selected composed management app factory (including all installed lifecycle/pipeline routers) with an explicit validated deterministic ManagementConfig, using a nonconnecting test database URL rather than load_config() or environment secrets and calls `app.openapi()` without lifespan/startup, opening a DB connection, contacting SMTP, or relying on a running HTTP server. Emit deterministic sorted JSON with a trailing newline; secret-bearing defaults/examples are excluded. `checkApiTypes.mjs` invokes that exporter from repository cwd and the locally installed locked generator; no fetching latest tool, remote schema, or live OpenAPI server in checks. Schema and TS changes are reviewed together. Once foundation tooling/artifacts are present, all downstream endpoint additions regenerate these two foundation-owned outputs and pass the same mandatory offline gate, including pipeline backend-only work. Before foundation exists, server use cases remain independently backend-testable; runtime API-only operation always stays independent of frontend tools.

Extend existing `.github/workflows/ci.yml` with separate frontend checks/browser jobs using exact Node/npm prerequisites, `npm ci`, `npm run check`, and locked local Playwright browser installation (`npm exec -- playwright install --with-deps chromium`) followed by `npm run test:e2e`. Backend Ruff/pytest jobs stay independent. Browser job builds the SPA and starts test API/SMTP fixtures as needed; reports preserve safe failure evidence. API-only backend runtime/tests/CLI do not require Node, node_modules, or dist. Frontend/schema-affecting changes must pass frontend jobs; absence of local tooling is an explicit unmet verification prerequisite, never a successful skip.

Extend existing `scripts/pre-commit-review.sh` with frontend lint/format checks when staged frontend files change; retain existing fast Python gates. Extend `scripts/pre-push-review.sh` with `npm --prefix frontend run check` when pushed changes affect frontend or the management/pipeline API schema, and browser checks for feature interaction changes against configured disposable fixtures. Detect changed paths against the pushed base, including backend schema-only edits; do not require Node for unrelated Python-only/API-runtime use. A required check with missing dependencies fails with setup guidance. Hooks do not install packages, fetch browsers, reset databases, scrape sources, or transmit reviews automatically. Keep hook installer semantics for configured hooks paths/worktrees.

#### Standards provenance

Repository facts were compared with `.worktrees/simple-matchmaking/src/huginn/management`, `matchmaking/application/protocols/clock.py`, `scripts/pre-commit-review.sh`, `scripts/pre-push-review.sh`, `.github/workflows/ci.yml`, `CLAUDE.md`, and `BEST_PRACTICES.md`. External guidance supports the tool choices, while the precise file inventory and scripts above are project decisions: [Node supported releases](https://nodejs.org/en/about/previous-releases), [npm clean installation](https://docs.npmjs.com/cli/v11/commands/npm-ci/), [Vue TypeScript](https://vuejs.org/guide/typescript/overview.html), [Vue tooling](https://vuejs.org/guide/scaling-up/tooling.html), [Vue testing](https://vuejs.org/guide/scaling-up/testing.html), [Vite getting started](https://vite.dev/guide/), [TypeScript strict](https://www.typescriptlang.org/tsconfig/strict.html), [typescript-eslint flat configuration](https://typescript-eslint.io/getting-started/), [Vue ESLint](https://eslint.vuejs.org/user-guide/), [Prettier installation](https://prettier.io/docs/install), [Vitest configuration](https://vitest.dev/config/), [Vue Test Utils](https://test-utils.vuejs.org/guide/), [Playwright accessibility testing](https://playwright.dev/docs/accessibility-testing), [OpenAPI TypeScript](https://openapi-ts.dev/introduction), [WCAG 2.2](https://www.w3.org/TR/WCAG22/), [PEP 8](https://peps.python.org/pep-0008/), [Python 3.14 Protocol](https://docs.python.org/3.14/library/typing.html#typing.Protocol), and [dataclasses](https://docs.python.org/3.14/library/dataclasses.html). Frozen values, execute use cases and exact layers are Huginn decisions; language documentation supplies syntax and interface semantics.

### 7. Exact foundation file inventory

Backend paths below are relative to `src/huginn/management/`; package `__init__.py` markers contain no re-export umbrellas.

| Exact path | Named types / exports |
| --- | --- |
| `application/requests/current_session_request.py` | CurrentSessionRequest (principal, session ID, raw token hidden from repr) |
| `application/responses/current_session_response.py` | CurrentSessionResponse (account_id, user_id, csrf_token hidden from repr, expires_at) |
| `application/services/current_session_service.py` | CurrentSessionService.execute(CurrentSessionRequest) -> CurrentSessionResponse; revalidates active session/account and atomically initializes stable digest using existing UoW/repositories |
| `security/csrf.py` | derive_csrf_token; purpose-separated HMAC helper reused by login/bootstrap |
| `security/csrf_policy.py` | CSRF_CONTEXT_VERSION |
| `presentation/api/responses/current_session.py` | CurrentSessionResponse HTTP model, separate namespace from application response |
| `presentation/api/dependencies/browser_origin.py` | require_same_origin_browser_mutation (login and later lifecycle reuse) |
| `presentation/api/static_assets.py` | mount_frontend_assets; bounded history fallback/cache policy |

Existing files updated narrowly: `application/services/authentication.py` (`AuthenticationService`, `_SessionOperations` use shared derivation), `persistence/contracts/repositories/session.py` (`SessionRepository` gains conditional digest initialization), `persistence/repositories/session.py` (`PostgresSessionRepository` implements atomic active-session update), `presentation/api/routers/sessions.py` (current GET route), `presentation/api/dependencies/services.py` (inject service), `app.py` (composition/optional assets), and `config.py` (`ManagementConfig` optional assets path). Reuse `presentation/api/dependencies/authentication.py`'s `Authenticated`, existing `Principal`, `Session`, `AuthenticationError`, `AuthorizationError`, `UnitOfWorkProtocol`, `UnitOfWork`, database client and safe HTTP handlers. No new entity, persisted row model, database port, repository, or UoW is required for foundation; existing session columns suffice. Application secret input originates only from the authenticated server dependency, never the browser payload. Service response is explicitly mapped into its HTTP response and never serializes the raw token.

Frontend paths below are relative to `frontend/`. Root `scripts/export-management-openapi.py` owns offline export; `scripts/frontend-review.sh` owns the shared conditional hook checks. Existing CI/hooks are extended as described above. The runtime runbook is `docs/web-ui-foundation.md`; the lasting decision is `adr/0016-browser-foundation-and-session-bootstrap.md`. Backend tests use separate `tests/management/test_current_session.py`, `test_current_session_integration.py`, `test_browser_origin.py`, `test_static_assets.py`, and `test_openapi_export.py` modules; `tests/browser_fixture.py` owns disposable real-API browser setup and `tests/test_frontend_hook_contracts.py` checks hook dispatch/failure behavior.

| Exact path | Named types / exports |
| --- | --- |
| `package.json` | scripts/dependency pins/engines/packageManager |
| `package-lock.json` | npm resolution lock |
| `.node-version` | exact Node 24 patch |
| `index.html` | Vite entry |
| `vite.config.ts` | Vite config |
| `tsconfig.json` | project references |
| `tsconfig.app.json` | strict application config |
| `tsconfig.node.json` | strict tooling config |
| `tsconfig.test.json` | strict isolated component/unit/browser test config |
| `env.d.ts` | Vite environment typing |
| `eslint.config.js` | flat ESLint config |
| `.prettierrc.json` | Prettier config |
| `.prettierignore` | generated/build/report ignores |
| `vitest.config.ts` | Vitest/jsdom config |
| `playwright.config.ts` | browser/fixture config |
| `scripts/checkApiTypes.mjs` | offline schema/type comparison |
| `DESIGN.md` | visual/interaction tokens |
| `src/main.ts` | SPA entry |
| `src/app/App.vue` | Vue root |
| `src/app/components/AppShell.vue` | shell |
| `src/app/components/AppNavigation.vue` | responsive navigation |
| `src/app/router.ts` | router |
| `src/app/queryClient.ts` | identity-scoped query client |
| `src/api/generated/openapi.json` | deterministic exported schema |
| `src/api/generated/schema.d.ts` | generated paths/components |
| `src/api/client.ts` | apiRequest |
| `src/api/normalizeApiError.ts` | normalizeApiError |
| `src/api/apiError.ts` | ApiError |
| `src/shared/theme/preset.ts` | PrimeVue preset |
| `src/shared/theme/tokens.css` | spacing/type/layout tokens |
| `src/shared/ui/PageHeader.vue` | header |
| `src/shared/ui/FieldFeedback.vue` | field errors |
| `src/shared/ui/LoadingState.vue` | loading |
| `src/shared/ui/EmptyState.vue` | empty |
| `src/shared/ui/ErrorState.vue` | errors |
| `src/shared/ui/StatusLabel.vue` | text status |
| `src/shared/forms/useDirtyDraft.ts` | useDirtyDraft |
| `src/shared/navigation/validateReturnPath.ts` | validateReturnPath |
| `src/features/session/pages/LoginPage.vue` | login |
| `src/features/session/components/LogoutAction.vue` | logout |
| `src/features/session/api/getCurrentSession.ts` | getCurrentSession |
| `src/features/session/api/login.ts` | login |
| `src/features/session/api/logout.ts` | logout |
| `src/features/session/composables/useSession.ts` | useSession |
| `src/features/session/sessionContext.ts` | SessionContext |
| `src/features/session/forms/loginDraft.ts` | LoginDraft |
| `tests/setup.ts` | component setup |
| `tests/unit/apiClient.test.ts` | 204/error/CSRF transport |
| `tests/unit/sessionBoundary.test.ts` | cache/expiry/403 boundary |
| `tests/unit/dirtyDraft.test.ts` | background refresh/draft behavior |
| `tests/components/LoginPage.test.ts` | submission interaction |
| `tests/components/SharedUi.test.ts` | shared status, feedback and action interactions |
| `tests/e2e/session.spec.ts` | login/reload/logout/multi-tab |
| `tests/e2e/accessibility.spec.ts` | axe and keyboard flows |

## Risks / Trade-offs

- [Old primary base] → Implement against the reviewed layered-management base or its merged successor; compare actual source before applying, never replay restructuring.
- [Legacy CSRF proof transition] → Atomic deterministic initialization, multi-tab tests, explicit 403 reload guidance, and no unsafe automatic replay.
- [Private query bleed] → Account-scoped keys plus unconditional cache clearing on authentication boundary changes.
- [Theme drift] → Standard component preset, shared tokens, representative screen review before multiplying pages.

## Migration Plan

No schema migration is needed for bootstrap. Deploy compatible session derivation/bootstrap before the frontend. Build static assets with a locked package manager and documented Node prerequisite; backend remains deployable without frontend artifacts. Record an ADR for the lasting browser/session design. Rollback removes the frontend mount and bootstrap endpoint, retaining legacy endpoints; restoring an older random-CSRF server requires new login for sessions whose proofs transitioned.
