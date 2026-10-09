## Context

See [proposal.md](proposal.md). This frontend consumes [pipeline-control-and-history](../pipeline-control-and-history/design.md); execution and permissions are owned by that server module. Foundation supplies current session/role, theme, shell, JSON/error transport and private query lifecycle. No operational endpoints exist at the inspected implementation base today, so console tests must use the new documented contracts and eventually real disposable-database API fixtures.

## Goals / Non-Goals

**Goals:** One Data collection tab at `/admin/pipeline` to start the supported collection pipeline and inspect invocation X's exact stage/source/history records plus the companies written by its managed Gold company stage.

**Non-Goals:** Job builder, source configuration, scheduler, cancellation, stage replay, operator reconciliation UI, raw log streaming, arbitrary SQL, matching jobs, or manual entity-review actions. Ingestion includes API-shaped sources as well as scraping; the Pull data action starts the existing collection pipeline.

## Decisions

### 1. Routable console and distinct views

| Placement | Responsibility |
| --- | --- |
| `features/pipeline/pages/PipelineHistoryPage.vue` | Existing `/admin/pipeline` route, labeled Data collection: history, validated filter/page and Pull data |
| `features/pipeline/pages/PipelineInvocationPage.vue` | `/admin/pipeline/invocations/:id`: summary, stage progress, stage tabs, event log and company results |
| `features/pipeline/components/InvocationSummary.vue` | ID, state, requester/times, freshness and safe error |
| `features/pipeline/components/StageExecutionTable.vue` | Ordered plan, exact dependencies, actual job state and metric labels |
| `features/pipeline/components/SourceExecutionList.vue` | Child job detail grouped by explicit parent-stage ID |
| `features/pipeline/components/InvocationEventLog.vue` | Cursor-paginated safe events |
| `features/pipeline/components/InvocationCompanyResults.vue` | Summary and bounded page of companies attributed to this invocation's managed Gold company write |
| `features/pipeline/api/` | Separate typed trigger/history/detail/events/company-results query and mutation adapters |

Use PrimeVue tabs/tables/status text and existing shared components. Keep the existing `/admin/pipeline` route and label its administrator navigation tab Data collection. Nested stage tabs have route query `stage=bronze|silver|gold`; history has state/offset query parameters. Validate UUID/filter/tab values. Deep links survive reload via foundation session bootstrap. Show History and Invocation detail clearly rather than every record as another open browser tab.

### 2. Invocation-oriented visual hierarchy

Top-level authenticated navigation includes Data collection only for role admin, using the existing `/admin/pipeline` route. Page header uses Pull data as primary action and states it runs the existing full HN/YC/EU-Startups pipeline; it does not imply a new scrape-only mode. History rows show requested timestamp, short/copyable invocation ID, status, requester, duration when known, and View invocation. No global company counts, fabricated trends, or completion cards.

Detail header shows exact invocation ID and status; metadata shows request/start/finish times and most recent tracking update. Source/Bronze includes aggregate ingestion, its hn/yc children, independent EU-Startups stage and its child. Silver shows three staging steps, shared resolution, and manual-review queueing; Gold shows company then company-signal writes. The plan contains nine known stages. Show “N of 9 stages finished,” where only succeeded, failed, and skipped stages count; running is excluded, and failed/skipped remain separately visible. Interrupted and not-executed stages stay distinct and do not increase the finished count. While a source is running, show its activity with an indeterminate progress bar because its row total is unknown. Do not derive any bar or percentage from elapsed time. Actual stage plan from server drives order/dependencies, not a hardcoded assumed success chain. Warnings distinguish dependency skip, execution interruption, unknown metric, and stale tracker. Use the browser locale to format times and retain UTC ISO tooltip/detail; elapsed duration is display-only and never determines result.

The invocation results summary counts only distinct companies attributed to that invocation's managed `gold.company` write and labels them processed/written by this run. A bounded paginated list shows only the API's allowlisted current Gold fields: ID, name, domain, business sector, country, company scale, company status, and writing stage job ID. It never displays Gold contact fields or private notes. State that these are companies written by the run, not necessarily newly discovered or changed; fields may reflect edits made after the run. Show loading, empty, page error, and retry states. A legacy invocation with no explicit attribution displays unavailable/unknown membership rather than an inferred count. Refetch the active company page when the invocation detail reports a change in the `gold.company` stage state/metrics or when the invocation becomes terminal, so new committed attributions appear. Cancel an in-flight company request on invocation navigation or query-scope change, and ensure its completion cannot populate another invocation's cache.

Event history sits below stage tabs with safe message, time and stage/source links. Display default first/latest bounded window then Load older/newer with correct cursor mechanics. Because the server cursor advances ascending sequence, fetch initial events from 0 in bounded pages; provide Next events rather than downloading all to reach last. Active updates poll from last displayed sequence; a gap/pending older page is visibly navigable and not skipped silently. No `v-html`, raw stderr, or downloadable secret-containing logs.

### 3. Trigger and uncertainty

Generate request_id with browser crypto UUID on the first deliberate Pull data click. Hold that ID in local component memory until result is known; disable duplicate submissions. 202 receipt navigates to detail. 409 safe detail offers Open active invocation. A network failure shows Check history and Retry same request; only a deliberate new run after resolving prior outcome generates another ID. Do not use automatic mutation retry. An uncertain browser reload loses memory; history remains authoritative and the user must inspect it before a new trigger. A later interrupted/failed terminal invocation may offer Pull data as a new deliberate full run, never Resume this invocation.

No extra modal confirmation is necessary for routine authorized manual trigger; state clearly it starts the existing shared pipeline. Queue/waiting is honest when worker unavailable or another operation holds the shared execution guard. A separately specified matchmaking operation may use the shared guard, but is not part of this page's pipeline stages or Pull data action. Errors use safe existing envelope mapping; unknown execution never becomes Failed based solely on a failed fetch.

### 4. Polling and cache lifecycle

Keys include Account identity and invocation ID. Detail polls every 3 seconds while queued/running, only when document visible and view mounted. Event polling starts after the last sequence already loaded and is limited 100/page; when `has_more` is true, offer/load one bounded page per iteration rather than unbounded loops. History refreshes at 10 seconds while visible if it contains active rows. Transient query retry uses exponential backoff capped 30 seconds; do not retry 401/403/404/422. Terminal detail stops polling after one final event fetch; navigation or hidden tab cancels outstanding requests via AbortController. Visibility return performs fresh GET. 403 clears pipeline queries, hides navigation, and displays forbidden; 401 uses foundation session teardown. Query data never authorizes a trigger.

### 5. Verification

Interaction tests cover 202 navigation,409 active reference, response-loss same-key retry, queued/worker-unavailable/stale states, every stage state, source associations, pagination/cursor merge, terminal polling stop, visibility/navigation abort, demotion/expiry, X-to-Y isolation and markup escaping. Render realistic IDs/messages/long names at wide/narrow sizes with keyboard access. Use real PostgreSQL 16-backed server runs with harmless deterministic injected executor fixtures for browser/API integration; real network scraping is not needed to prove console state contracts and must not be triggered by UI tests. No shared database reset.

## Risks / Trade-offs

- [Cached role differs from server] → API 403 immediately stops controls/data; server always enforces role.
- [Polling cost] → Visible active-page scope, bounded intervals/pages and query cancellation.
- [Large event history] → Explicit cursor navigation and bounded slices; no giant log download.
- [Unknown trigger outcome] → Stable request ID and history reconciliation, no new implicit run.

## Migration Plan

Ship after foundation session-role extension and pipeline server endpoints. Feature navigation appears only for server role admin with deployed contracts. No schema changes here. Rollback removes console routes without losing persisted invocation history. Verify against real backend and user/admin/disabled-account fixtures before enabling the tab.

## Shared standards dependency

The authoritative [foundation implementation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) govern this change: exact Node/npm/dependency locks, strict TypeScript, naming, offline schema drift, lint/format/test/CI/hook gates, WCAG 2.2 AA target, and Python layer placement. Consume shared components and transport; do not introduce divergent tooling or duplicate session/database ports. The inventories below define the new production files/types for this feature. Package `__init__.py` markers are empty, not public re-export umbrellas. Test files mirror these use cases and add the behavior scenarios already specified in this design.

## Exact administrator frontend inventory

Relative to `frontend/src/features/pipeline/`; HTTP shapes are generated foundation types, not manually redeclared entities/read models. Existing app router/navigation adds role-gated routes using foundation session context.

| Exact path | Named types / exports |
| --- | --- |
| `pages/PipelineHistoryPage.vue` | PipelineHistoryPage |
| `pages/PipelineInvocationPage.vue` | PipelineInvocationPage |
| `components/InvocationSummary.vue` | InvocationSummary |
| `components/StageExecutionTable.vue` | StageExecutionTable |
| `components/SourceExecutionList.vue` | SourceExecutionList |
| `components/InvocationEventLog.vue` | InvocationEventLog |
| `components/InvocationCompanyResults.vue` | InvocationCompanyResults |
| `components/RunPipelineAction.vue` | RunPipelineAction |
| `api/triggerInvocation.ts` | triggerInvocation |
| `api/listInvocations.ts` | listInvocations |
| `api/getInvocation.ts` | getInvocation |
| `api/listInvocationEvents.ts` | listInvocationEvents |
| `api/listInvocationCompanies.ts` | listInvocationCompanies |
| `composables/usePipelineHistory.ts` | usePipelineHistory |
| `composables/usePipelineInvocation.ts` | usePipelineInvocation |
| `composables/useInvocationEvents.ts` | useInvocationEvents |
| `composables/useInvocationCompanies.ts` | useInvocationCompanies; bounded offset pagination and invocation-scoped cache |
| `composables/usePipelineTrigger.ts` | usePipelineTrigger; stable request identity |
| `navigation/validatePipelineQuery.ts` | validatePipelineQuery |
| `formatting/formatPipelineMetric.ts` | formatPipelineMetric |
| `formatting/formatPipelineTime.ts` | formatPipelineTime |
| `routes.ts` | pipelineRoutes |
