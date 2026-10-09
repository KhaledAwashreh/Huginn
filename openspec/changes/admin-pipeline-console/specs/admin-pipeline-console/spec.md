## Purpose

Let administrators trigger the supported pipeline and inspect invocation-specific progress, stages, source detail, and durable operational history.

## ADDED Requirements

### Requirement: Administrator-only pipeline navigation
The browser SHALL expose the Data collection tab at the existing `/admin/pipeline` route only when current session bootstrap reports administrator role. Direct administrator routes SHALL show a safe forbidden state for ordinary users. Server 403 SHALL immediately disable administrator controls even when cached role data are stale; server authorization remains authoritative.

#### Scenario: Role revoked while console open
- **WHEN** a console request returns 403 after administrator demotion
- **THEN** further trigger/poll actions stop, operational query data are cleared, and a forbidden state is shown.

### Requirement: Manual trigger with invocation identity
The Data collection page SHALL offer Pull data for the configured full HN/YC/EU-Startups pipeline, explain that it starts the existing collection flow, and prevent duplicate submission. It SHALL generate one client request ID per deliberate trigger attempt and retain it across response uncertainty. Successful 202 SHALL navigate to that invocation. Active-run 409 SHALL offer the authorized existing invocation, and uncertain network outcome SHALL offer history inspection and an explicit same-ID retry rather than generating another request ID automatically.

#### Scenario: Pull data accepted
- **WHEN** an administrator starts a new run
- **THEN** the console navigates to the returned invocation ID and shows its queued status without claiming execution already started.

#### Scenario: Trigger outcome unknown
- **WHEN** the request response is lost
- **THEN** the console explains uncertainty and lets the administrator check history or explicitly repeat the same request ID, never silently create a new invocation.

### Requirement: Invocation-specific stage tabs
Invocation detail SHALL identify its ID, requester, requested/start/finish times, result, and tracking freshness. It SHALL provide Source/Bronze, Silver, and Gold tabs with all planned stages in order, actual state, declared dependencies, per-source child jobs, known metric labels/units, and safe failure/skip reasons. Pending, running, succeeded, failed, skipped, and interrupted/not-executed states SHALL be visually and textually distinct. Manual-review queueing SHALL appear within Silver without adding manual review actions.

#### Scenario: Source and aggregate stage
- **WHEN** an invocation's aggregate ingestion stage contains HN and YC child runs
- **THEN** the Source/Bronze tab shows separate child states and exact parent association, not one guessed source total.

#### Scenario: Dependency skip
- **WHEN** a stage is skipped because its dependency did not succeed
- **THEN** the page says it was skipped, names the failed/unmet dependency safely, and distinguishes it from a stage that ran and failed.

### Requirement: Honest progress and stale tracking
The console SHALL display observed stage states, timestamps, elapsed duration, and typed counters. It SHALL label progress “stages finished” and count only succeeded, failed, or skipped stages out of nine; running stages are excluded, and failed/skipped remain distinct visible outcomes. Interrupted and not-executed stages remain distinct and do not increase the finished count. Ongoing source work SHALL use an indeterminate progress bar because no row denominator is known. No progress bar or percentage may be derived from elapsed time. Unknown counters SHALL display as unknown. It SHALL not reinterpret failed-source count as rows written or infer completion from a stopped clock. Stale worker tracking SHALL be visible with last-update time and recovery guidance; the console SHALL not offer unimplemented cancel/restart/reconcile buttons.

#### Scenario: Stale running invocation
- **WHEN** detail reports a running invocation with stale heartbeat
- **THEN** the console displays stale tracking and trusted-operator recovery guidance without calling it completed or starting another run.

#### Scenario: Nine-stage progress with failure and skip
- **WHEN** an invocation has nine planned stages, including failed and dependency-skipped stages, and one source remains active
- **THEN** the page shows “N of 9 stages finished,” where N counts only succeeded, failed, and skipped stages, identifies failed and skipped stages separately, and uses an indeterminate bar for the active source without deriving progress from elapsed time.

### Requirement: Invocation company results
Invocation detail SHALL show a summary and paginated list only for companies explicitly attributed to that invocation's managed `gold.company` write. The list SHALL page through the administrator-only API with a requested limit no greater than 100, show only current Gold `id`, `name`, `domain`, `business_sector`, `country`, `company_scale`, `company_status`, and `stage_job_run_id`, and scope every query/cache key to the selected invocation. It SHALL exclude Gold contact fields and `notes`. It SHALL refetch the active company page when the observed `gold.company` stage state/metrics change or when the invocation becomes terminal. Navigation or invocation-scope changes SHALL cancel the prior request and prevent its response from entering another invocation's cache. Labels SHALL state companies were processed or written by this run and SHALL NOT claim they are new or changed. Loading, empty, page error, and retry states SHALL be visible. Missing attribution for legacy invocations SHALL be shown as unknown/unavailable and SHALL NOT be inferred from source counts, stage totals, or time proximity.

#### Scenario: Gold write results
- **WHEN** invocation X has explicit attribution rows for companies committed by its `gold.company` job
- **THEN** the detail page shows their current Gold fields in bounded pages and labels the count as companies processed/written by this run.

#### Scenario: Legacy or empty attribution
- **WHEN** invocation X predates explicit company attribution or committed no company writes
- **THEN** the page shows unknown membership for legacy data or a truthful empty result for known zero, without constructing company IDs from aggregate metrics.

#### Scenario: Refresh after Gold results change
- **WHEN** invocation detail reports a changed `gold.company` stage state/metrics or reaches a terminal state while a company page is open
- **THEN** the page refetches the selected invocation's company results, and a response from a canceled request cannot populate another invocation's view.

### Requirement: Bounded polling and errors
The console SHALL poll only the selected active invocation while its page is visible, with bounded intervals and transient retry backoff. It SHALL stop on terminal state, navigation, hidden page, session expiry, or forbidden response; resume with a fresh fetch when appropriate. Transient fetch failures SHALL preserve last known data and clearly identify its age.

#### Scenario: Transient network failure
- **WHEN** one detail poll fails after previous successful reads
- **THEN** the console retains the last known view with a refresh-failed notice and retries with bounded backoff, without showing a new run or a false failure result.

### Requirement: History and event log
The console SHALL provide paginated newest-first invocation history, state filtering, direct links to detail, a separately paginated chronological event log, and independently paginated company results for the selected invocation. It SHALL use server cursors/offsets and IDs to merge active updates without duplicates, support older events and company result pages without downloading unbounded data, and render event messages as text rather than executable HTML.

#### Scenario: Switch invocation
- **WHEN** an administrator navigates from invocation X to Y
- **THEN** stage and event queries are scoped to Y, polling for X stops, and X's events are not appended to Y's log.

#### Scenario: Untrusted message text
- **WHEN** a sanitized operational message contains markup-like characters
- **THEN** the browser displays them as text without script or HTML execution.

### Requirement: Usable operational layouts
The console SHALL support keyboard navigation, visible focus, non-color status labels, long invocation IDs, long safe messages, and narrow viewports. Queued/empty/loading/error/forbidden/terminal states SHALL retain clear task context and expose only supported actions. The page SHALL not expose matcher execution as a collection stage or Pull data option; a separate admin matchmaking operation may serialize through the shared guard.

#### Scenario: Narrow stage table
- **WHEN** an administrator opens detail on a narrow viewport
- **THEN** stage names, status, and detail actions remain readable/reachable through deliberate scrolling or stacked detail layout.

### Requirement: Shared standards and explicit placement
Implementation SHALL comply with the authoritative [foundation standards](../../../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) and this change's exact design inventory. New application ports SHALL use `application/protocols`; existing persistence conventions SHALL be preserved. Domain SHALL not import application/read-model/HTTP/persistence types. New Python value types SHALL be frozen dataclasses and new application use cases SHALL expose `execute(Request) -> Response`. Pyright adoption remains deferred. Schema changes SHALL regenerate the shared offline OpenAPI/TypeScript artifacts and pass the drift gate.

#### Scenario: Review implementation placement
- **WHEN** this change adds a service, type, query projection, repository, row model, or browser feature
- **THEN** its named file and dependency direction follow the exact design inventory and shared conventions without duplicate session/database/tooling definitions.

### Requirement: Reproducible browser verification
Browser implementation SHALL use the foundation's pinned Node/npm lockfile, strict SFC/tooling type checks, ESLint/Prettier, Vitest/Vue Test Utils, Playwright/axe, and named CI/hook gates. User-facing pages SHALL target WCAG 2.2 AA with manual keyboard/focus/reflow/contrast checks supplementing automated scans. API-only startup SHALL remain independent of Node and frontend build artifacts.

#### Scenario: Required browser gate
- **WHEN** a browser feature or API schema changes
- **THEN** its applicable foundation checks fail on type/lint/format/schema/interaction errors and missing prerequisites are reported rather than treated as a passing skip.
