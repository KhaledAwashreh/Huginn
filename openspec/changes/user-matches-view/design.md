## Context

See [proposal.md](proposal.md) for the user need and [specs/user-matches-view/spec.md](specs/user-matches-view/spec.md) for externally visible behavior. The inspected application base is `.worktrees/user-configuration-workspace` at `7fc076a646af23d7502f9754f62dfdcb97ed04c4`, with the configuration workspace and several generated/API files present as uncommitted worktree changes. It has synchronous FastAPI management routes, explicit application services and PostgreSQL repository boundaries, authenticated `Principal.user_id`, a shared offset/limit page response capped at 100, and a Vue Router/Query application with an identity-cleared cache. The operational schema already has `operational.match`; Gold has one current `gold.company` row and current `gold.company_signal` facts. The match row has no originating strategy/run/evidence fields, so current company data cannot establish why the row was created.

The root checkout contains planning artifacts, but the implementation baseline is the named worktree or its merged successor. Compare source before applying; do not reconstruct foundation or configuration changes from this plan. The shared standards in [web-ui-foundation/design.md](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) govern tooling, API type generation, session/query isolation, accessibility, and feature inventory. The product dependency chain is `web-ui-foundation` → `user-configuration-workspace` and `admin-matchmaking-execution` → this change; `admin-pipeline-console` frontend work is independent.

## Goals / Non-Goals

**Goals:** Add a read-only owner-scoped query path through the existing management architecture; show current company and signal context with clear provenance; provide a bounded Matches browser feature; give empty states truthful active-strategy and durable-evaluation context.

**Non-Goals:** Create a second app server, add matching execution or scheduling, make a company-directory endpoint, create `operational.match` rows, change match status or notes, add scoring/rationale history, or implement CRM, activity, communication, feedback, or outreach actions.

## Decisions

### 1. Put authenticated read use cases in management

The existing management app owns the signed-in HTTP boundary and already supplies an authenticated principal, exception mapping, OpenAPI export, a PostgreSQL unit of work, and owner-scoped repository conventions. Add a focused `matches` read feature to that boundary instead of exposing matchmaking CLI internals, creating another ASGI app, or adding endpoints that accept a company ID. Every query receives the principal's user ID from authentication; clients cannot supply or override it. A match detail lookup filters by both match ID and user ID, and the signal query first establishes that the match belongs to that user before selecting facts by its company ID. Missing and other-owner IDs map to the same 404.

Keep transport requests/responses, application services, application read models and query protocol, persistence query adapter, strict row models, and HTTP response models in their respective existing layers. The read models are query projections, not domain entities. Use four narrow use cases: list matches, get one match, list signals for an owned match, and get the overview. Use the existing page convention (`limit=50`, `offset=0`, `1 <= limit <= 100`) and the established `PageResponse`, not a new cursor protocol. Match pages order by `(operational.match.created_at DESC, operational.match.id DESC)`; signal pages order by `(gold.company_signal.occurred_at DESC, gold.company_signal.id DESC)`. The detail response can reuse the same match/current-company read model as a list item.

### 2. Read the current Gold model as context

Join matches to the current company row for `name`, `domain`, `business_sector`, `country`, `company_scale`, and `company_status`; expose the match's stored status, notes, `created_at`, and `updated_at`. The separate signal page reads `signal_type`, `source`, `source_url`, `description`, `stage`, `occurred_at`, and `ingested_at` from `gold.company_signal`. Do not read `gold.company_history` or infer the state at match creation. Do not surface score, feature breakdown, or feedback as rationale; these are separate operational tables and do not provide an origin link. Notes are existing stored text and are rendered as text.

The endpoints are `GET /api/v1/matches`, `GET /api/v1/matches/{match_id}`, `GET /api/v1/matches/{match_id}/signals`, and `GET /api/v1/matches/overview`. Register the overview route before the parameter route. The list accepts `status`, `limit`, and `offset`; the signals route accepts `limit` and `offset`. No route accepts `company_id` or causes a write. All four routes use the existing `Authenticated` dependency; no CSRF proof is needed for GET. Every response from these private endpoints, including authentication, authorization, not-found, validation, and server errors, carries `Cache-Control: no-store` and `Vary: Cookie`; use an exception-safe response policy so error handlers retain both headers.

### 3. Make overview truth depend on durable per-user outcomes

The overview query reports `has_matches` using an owner-wide `EXISTS` over `operational.match`, independent of current list filter and offset. It combines that flag and the current user's active-strategy existence with the latest durable per-user result from the run projection owned by `admin-matchmaking-execution`. Do not derive match existence from a page slice or evaluation history from `operational.match.created_at`, because a match can be outside the current status/page, predate a run, survive multiple runs, or be updated independently. Query `ops.matchmaking_run_users` joined to `ops.matchmaking_runs`, constrained by the authenticated user's ID, ordered by `run.requested_at DESC, run.id DESC`, and return only the current user's latest summary. The projection's result state is one of `pending`, `running`, `succeeded`, `disabled_user`, `user_not_found`, `failed`, `commit_outcome_unknown`, or `not_executed`; it includes requested/started/finished timestamps, cutoff/as-of timestamps, strategy counts, newly created match count, existing-match skip count, and `tracking_stale` derived from the run heartbeat for an active owner target. Do not expose run ID, requester, sibling users, run totals, or raw errors. Count fields are populated only for acknowledged `succeeded` results. The management overview returns `has_matches`, `has_active_strategies`, and this narrow latest-result summary. A missing run history means no recorded managed evaluation; legacy CLI work is not tracked and SHALL NOT be described as never executed. Pending, running, stale, failed, and otherwise incomplete results remain unknown, never completed-with-zero. This change depends on the shared tables and exact result contract from `admin-matchmaking-execution`; no cross-package service import is added.

The UI gives slice emptiness precedence over account-level empty context. If a selected status/page returns no rows, show a filter/page-specific empty state with clear-filter and/or first-page actions; do not infer overall absence or evaluation state from that slice. For an unfiltered nonzero offset with an empty page and `has_matches: true`, offer a first-page action. Only an unfiltered first page with no rows and `has_matches: false` uses the overall empty-state explanation: no active strategy explains how to begin; active strategy with no recorded managed run says no managed evaluation is recorded; an acknowledged successful result with zero new matches says no new matches came from that evaluation; any other run state, stale active target, or unavailable overview says evaluation status is pending or unavailable. If existing matches are present, list them regardless of the latest run count. Overview read failure shows a recoverable context error and never changes the match list response.

### 4. Keep list and detail as separate feature-owned queries

Add `features/matches/` to the existing router and navigation metadata. `/matches` owns the status filter, offset pagination, newest-first rows, and overview query for its empty state. `/matches/:id` loads the owner-scoped match detail and its separate offset-paginated signals. Use account-scoped query keys under the current session identity; the foundation query client clears private data at identity or session-proof boundaries. Keep list, detail, signals, and overview API adapters and query composables as separate modules so each has one response type and retry behavior.

Use shared `PageHeader`, `LoadingState`, `EmptyState`, `ErrorState`, and `StatusLabel`. Do not override the foundation QueryClient's disabled automatic query retries; 401, 403, 404, and 422 responses are never automatically retried. Preserve already-loaded list rows while a filter/page is loading and offer deliberate retry only for recoverable network or server errors. Filter changes reset the offset to zero. The detail heading and list entries use the match ID as a stable identity; signal paging remains independent so a signal failure does not hide match/company fields. Status labels always include text and use the management domain's stable `MatchStatus` value object with the vocabulary `new`, `contacted`, `responded`, `dismissed`, and `converted`; the query and UI share these recognized values without importing matcher internals.

Render `domain` and `source_url` only through a small pure external-link validator. Construct a company URL only after the stored domain passes a hostname-only check; use an explicit `https://` scheme. For stored signal URLs require a parseable, explicit `http:` or `https:` scheme; reject protocol-relative values, credentials, malformed or nested URL input, and all other schemes. Set `target="_blank"` links to `rel="noopener noreferrer"`; display rejected values as plain text. Never use `v-html` for company notes, signal descriptions, domains, or URLs.

### 5. Exact production inventory

Python paths are relative to `src/huginn/management/` unless rooted from the repository. New types are listed so implementation can preserve layer ownership without collapsing the read API into a single umbrella module.

| Exact path | Types / responsibility |
| --- | --- |
| `domain/value_objects/match_status.py` | `MatchStatus` stable management vocabulary for supported match states |
| `application/read_models/current_company.py` | `CurrentCompany` projection for current public Gold fields |
| `application/read_models/user_match.py` | `UserMatch` projection with owner match fields and `CurrentCompany` |
| `application/read_models/current_company_signal.py` | `CurrentCompanySignal` projection |
| `application/read_models/evaluation_summary.py` | `EvaluationSummary` projection for managed result state and stale flag |
| `application/read_models/matches_overview.py` | `MatchesOverview` projection combining owner-wide match existence, active-strategy existence, and latest result |
| `application/requests/list_matches_request.py` | `ListMatchesRequest` (`status`, `limit`, `offset`) |
| `application/requests/get_match_request.py` | `GetMatchRequest` |
| `application/requests/list_match_signals_request.py` | `ListMatchSignalsRequest` (`match_id`, `limit`, `offset`) |
| `application/requests/get_matches_overview_request.py` | `GetMatchesOverviewRequest` |
| `application/responses/list_matches_response.py` | `ListMatchesResponse`, existing `Page` envelope |
| `application/responses/get_match_response.py` | `GetMatchResponse` |
| `application/responses/list_match_signals_response.py` | `ListMatchSignalsResponse` |
| `application/responses/get_matches_overview_response.py` | `GetMatchesOverviewResponse`, including owner-wide `has_matches` |
| `application/services/list_matches_service.py` | `ListMatchesService` |
| `application/services/get_match_service.py` | `GetMatchService`, raises existing domain `NotFoundError` for non-owned IDs |
| `application/services/list_match_signals_service.py` | `ListMatchSignalsService`, requires an owned match |
| `application/services/get_matches_overview_service.py` | `GetMatchesOverviewService` |
| `application/protocols/matches_query.py` | `MatchesQuery` protocol returning application read-model projections |
| `persistence/row_models/current_company.py` | `CurrentCompanyRow` strict validation/mapping |
| `persistence/row_models/user_match.py` | `UserMatchRow` validation/mapping |
| `persistence/row_models/current_company_signal.py` | `CurrentCompanySignalRow` strict validation/mapping |
| `persistence/row_models/evaluation_summary.py` | `EvaluationSummaryRow` strict validation/mapping |
| `persistence/row_models/matches_overview.py` | `MatchesOverviewRow` strict validation/mapping |
| `persistence/queries/matches_query.py` | `PostgresMatchesQuery`; parameterized, owner-scoped SQL mapped through row models; no writes |
| `presentation/api/requests/matches.py` | strict `MatchStatusFilter` and query validation |
| `presentation/api/responses/current_company.py` | `CurrentCompanyResponse` |
| `presentation/api/responses/user_match.py` | `UserMatchResponse` composed with current company response |
| `presentation/api/responses/current_company_signal.py` | `CurrentCompanySignalResponse` |
| `presentation/api/responses/evaluation_summary.py` | `EvaluationSummaryResponse` |
| `presentation/api/responses/matches_overview.py` | `MatchesOverviewResponse` |
| `presentation/api/routers/matches.py` | `GET` routes, explicit application-to-HTTP mapping, private response headers |

Update only the existing composition files to wire the four services, `PostgresMatchesQuery`, and router: `app.py`, `presentation/api/dependencies/services.py` if providers are needed, and frontend-owned OpenAPI artifacts after regenerating them through the foundation exporter. Add the feature-specific API schema and route update, not another router or app factory. Reuse management auth, `Principal`, `UnitOfWork`, domain errors, common pagination response, and database connection handling. Application services depend on `MatchesQuery`; persistence does not implement a domain repository returning application projections.

Frontend paths are relative to `frontend/src/`.

| Exact path | Types / responsibility |
| --- | --- |
| `features/matches/routes.ts` | authenticated `/matches` and `/matches/:id` routes with navigation label |
| `features/matches/api/listMatches.ts` | typed list request |
| `features/matches/api/getMatch.ts` | typed detail request |
| `features/matches/api/listMatchSignals.ts` | typed signal-page request |
| `features/matches/api/getMatchesOverview.ts` | typed overview request |
| `features/matches/composables/useMatches.ts` | owner/session-scoped list query and filter/page state |
| `features/matches/composables/useMatch.ts` | detail query |
| `features/matches/composables/useMatchSignals.ts` | independently paged signal query |
| `features/matches/composables/useMatchesOverview.ts` | overview query used for empty state |
| `features/matches/lib/externalCompanyUrl.ts` | `companyWebsiteUrl` and `safeSourceUrl` validators |
| `features/matches/components/MatchStatusFilter.vue` | text-labeled supported status selector |
| `features/matches/components/MatchList.vue` | match rows and pagination controls |
| `features/matches/components/MatchOverviewEmptyState.vue` | empty-state copy mapped from explicit overview states |
| `features/matches/components/MatchSignals.vue` | current-context label, signal rows, independent pagination |
| `features/matches/pages/MatchesPage.vue` | list, filter, empty, loading, and recoverable error states |
| `features/matches/pages/MatchDetailPage.vue` | owner detail plus current company/signals sections |

Update `app/router.ts` to install the feature routes. Generated `frontend/src/api/generated/openapi.json` and `schema.d.ts` are foundation-owned outputs and must be regenerated from the composed app after adding the route.

### 6. Verification inventory and grouping

Use focused groups that establish authorization, query contract, truthfulness, and browser behavior rather than one test per field. Backend tests extend the existing management suite: `tests/management/test_matches_read_service.py` covers service ownership/not-found and overview state mapping; `tests/management/test_matches_read_router.py` covers authentication, query validation, response mapping, equivalent 404s, and private response headers on success and errors; `tests/management/test_matches_query_integration.py` uses disposable PostgreSQL to verify joins, owner scoping, stable order, status/pagination, signal scoping/order, and unchanged rows. Include overview integration against the `admin-matchmaking-execution` schema and exercise a missing/incomplete per-user result as unknown.

Frontend tests belong under `frontend/tests/unit/matches/` (`externalCompanyUrl.test.ts` and `matchesQueries.test.ts`) and `frontend/tests/components/MatchesWorkspace.test.ts`; cover unsafe URLs, filter/page reset, identity cache clearing, no automatic retry for terminal 401/403/404/422 errors, empty-state truth table, list/detail loading and error behavior, and accessible status/context labels. One browser flow in `frontend/tests/e2e/matches.spec.ts` covers authenticated list-to-detail navigation, filtering/paging, and owner isolation. Run the existing offline OpenAPI/type drift gate and foundation frontend checks when implementing. Do not add a server process, browser download, external dependency, or new test framework.

## Risks / Trade-offs

- [Match schema has no original run, strategy, or evidence relation] → Label Gold company fields and signals as current context and never reconstruct historical qualification.
- [A run without a durable successful per-user result can resemble zero matches] → Only a completed owner result with a known count is `completed`; missing or incomplete outcome is `unknown`.
- [Operational data is owner-specific while Gold is shared] → Every match query starts from `operational.match` constrained by authenticated `user_id`; signal reads require the owned match before company ID is used.
- [External URL fields come from source data] → Validate schemes and domain syntax before creating links; unsafe values remain plain text.
- [The base worktree contains uncommitted implementation files] → Apply on the reviewed source tree or its merged successor, compare the current file inventory first, and avoid replaying already-installed foundation/configuration changes.

## Migration Plan

There is no schema or data migration. Deploy the `admin-matchmaking-execution` owner-result projection before enabling overview evaluation states, then deploy the read API and frontend with the configuration/foundation dependencies available. Rollback removes the Matches navigation/routes and read router; match, strategy, Gold, and run data remain untouched. The management runtime stays usable without frontend build artifacts or Node.
