## Purpose

Provide safe administrator-triggered pipeline invocations with durable execution, explicit stage/source identity, and inspectable operational history.

## ADDED Requirements

### Requirement: Server-authoritative administrator access
Every pipeline trigger, history, detail, and event endpoint SHALL require an authenticated active administrator account. Ordinary users SHALL receive generic 403 and unauthenticated callers generic 401. Roles SHALL be assigned through trusted operator tooling only, default to user for public and existing accounts, and be rechecked server-side on each request; browser navigation SHALL not grant permissions.

#### Scenario: Self-promotion rejected
- **WHEN** a public signup or profile PATCH supplies administrator role
- **THEN** the request is rejected and no pipeline permission is gained.

#### Scenario: Role revoked with live session
- **WHEN** an administrator is demoted while their session remains active
- **THEN** subsequent pipeline requests are forbidden without waiting for session expiry.

### Requirement: Durable manual trigger
An authorized CSRF-protected trigger SHALL atomically persist an invocation, its immutable known stage plan, trigger identity, client request identity, and initial history event before returning 202 with invocation ID and detail location. Admission SHALL use a short transaction advisory lock in the independent `pipeline-trigger` namespace. The HTTP trigger SHALL NOT acquire or wait on the long-lived session advisory lock in the shared `shared-execution` namespace; accepted work waits for worker/CLI/matcher execution admission after the request returns. Work SHALL run outside the HTTP request. Trigger input SHALL not accept arbitrary commands, URLs, credentials, DSNs, source configuration, stage selection, scheduler parameters, or matching jobs.

#### Scenario: Trigger returns before execution
- **WHEN** an administrator triggers the configured full pipeline
- **THEN** a queued invocation is committed and 202 returns promptly even if no worker is running.

#### Scenario: Response lost after commit
- **WHEN** the trigger response is lost and the same administrator repeats the same client request ID
- **THEN** the existing invocation is returned without creating or executing a second invocation.

#### Scenario: Execution guard is held during trigger admission
- **WHEN** a supported full-pipeline CLI or separate matchmaking executor holds the shared session execution lock
- **THEN** the HTTP trigger does not wait on that lock, returns its normal accepted receipt or pipeline-queue conflict based on managed invocation state, and any accepted pipeline work waits for the execution guard.

### Requirement: Bounded exclusive execution
The system SHALL permit at most one queued/running managed invocation at a time and at most one full-pipeline execution across managed worker and supported full-pipeline CLI entrypoints. A distinct concurrent trigger SHALL return 409 identifying the authorized active invocation. Workers SHALL claim committed work safely across competing processes, hold the shared execution guard for the run, and preserve queued work across process restart. A separately specified administrator matchmaking operation may extend the guard additively and use the same guard/advisory resource; this pipeline SHALL claim only the pipeline resource and SHALL NOT invoke or import matcher execution.

#### Scenario: Simultaneous triggers
- **WHEN** two administrators submit distinct trigger requests concurrently
- **THEN** only one queued invocation is created and the other receives 409 with its active invocation reference.

#### Scenario: Competing workers
- **WHEN** two worker processes attempt to claim the same queued invocation
- **THEN** only one starts its pipeline and no stage runs twice through that claim.

#### Scenario: Guard connection lost during a fetch
- **WHEN** the execution-lock connection disappears while an old executor still has live fetch/write threads
- **THEN** its durable admission gate continues to block managed and full-CLI executors until the old executor is proven stopped, even though the advisory lock has been released.

#### Scenario: Pipeline waits for a shared-guard matcher
- **WHEN** a separately managed matchmaking run owns the shared execution guard
- **THEN** the pipeline worker leaves accepted work queued and a supported full-pipeline CLI exits busy until that matcher is proven stopped and releases its matching guard ownership.

### Requirement: Preserve existing pipeline semantics
Managed execution SHALL run the currently implemented full pipeline for HN, YC, and EU-Startups using the existing stage order, source isolation, parsing, retries, and dependency graph. A stage SHALL run only after every declared dependency succeeds; unrelated branches SHALL continue after a stage failure. OpenCorporates SHALL not be presented as supported full-pipeline work. Matching, scoring, delivery, and resurfacing SHALL not run as pipeline stages.

#### Scenario: HN/YC aggregate ingestion fails
- **WHEN** either source fails within aggregate ingestion
- **THEN** the aggregate stage is failed, both HN and YC staging stages are skipped per their existing aggregate dependency, and independent EU-Startups ingestion still proceeds.

#### Scenario: Shared resolution dependencies
- **WHEN** any of HN, YC, or EU-Startups staging fails or is skipped
- **THEN** shared Silver resolution is skipped and its dependent manual-review/Gold stages do not run against stale staging data.

### Requirement: Explicit invocation linkage
Every stage and ingestion-source execution in a managed run SHALL carry its invocation ID. Source records SHALL additionally identify their parent stage execution. Distinct source/stage names SHALL remain distinct identities; grouping SHALL not be inferred from timestamps, source text, or adjacent row order. Legacy unlinked job rows SHALL remain readable in their original form but SHALL not be attributed to a fabricated invocation.

#### Scenario: Stage and source both recorded
- **WHEN** invocation X runs aggregate ingestion with HN and YC child source jobs
- **THEN** both children reference invocation X and the exact aggregate stage job ID while Bronze run IDs continue to identify the source job that wrote them.

### Requirement: Honest stage progress and metrics
Invocation detail SHALL expose a persisted plan of nine stages, stage identity/order/dependencies, pending/running/terminal state, source children, timestamps, and typed observed metrics. Stage progress SHALL show “stages finished” as the count of succeeded, failed, or skipped stages out of nine; running stages are excluded from this numerator, and the labels SHALL retain failed and skipped as distinct outcomes. Interrupted and not-executed stages SHALL remain distinct from succeeded, failed, and dependency-skipped states and SHALL NOT increase the finished count. An active source with unknown row denominator SHALL use indeterminate progress. No progress percentage SHALL be derived from elapsed time. Existing job states running/succeeded/failed/skipped SHALL retain their meanings; pending is a plan state before a job exists. Unknown row counters SHALL remain unknown. Aggregate ingestion's failed-source count SHALL NOT be displayed as rows written or percentage completion. Any percentage SHALL use an explicitly supplied measured denominator.

#### Scenario: Pending plan visibility
- **WHEN** invocation X is queued or early in execution
- **THEN** every planned stage is visible as pending or its actual state, without manufacturing job rows that claim execution occurred.

#### Scenario: Ingestion completion counter
- **WHEN** aggregate ingestion finishes with value 0 meaning no failed sources
- **THEN** detail labels it as failed sources and does not report zero rows ingested based on that value.

### Requirement: Invocation-scoped Gold company attribution
For managed invocations, `CompanyWriter.write_all()` SHALL preserve its existing whole-batch transaction scope, entering `self._repository` for that batch. `elt/materialization.py` SHALL pass the invocation and exact `gold.company` stage job context into the writer. The `CompanyRepositoryPort.upsert_company()` contract SHALL return the persisted UUID; both INSERT and UPDATE branches of `build_upsert_query()` SHALL return `id`, and the repository SHALL use that ID to insert attribution through the same open repository/cursor. The system SHALL NOT commit per company or write attribution on another connection. `(invocation_id, company_id)` SHALL uniquely identify an attribution; a composite foreign key SHALL ensure `(invocation_id, stage_job_run_id)` refers to a job run linked to that same invocation, and the managed writer context SHALL be validated as the `gold.company` stage. If the batch rolls back, its Gold writes and all attribution rows SHALL roll back together; earlier separately committed pipeline stages remain intact. New invocations SHALL explicitly be marked as attribution-tracked; pre-existing invocations SHALL remain marked unknown legacy. The administrator-only company-results endpoint SHALL return at most 100 rows per page, scoped to the requested invocation, with deterministic ordering and no-store caching, plus the tracking state needed to distinguish known zero from unknown legacy. Company results SHALL expose only `id`, `name`, `domain`, `business_sector`, `country`, `company_scale`, `company_status`, and `stage_job_run_id` from current Gold data; contact fields and `notes` SHALL NOT be returned. Results SHALL NOT claim that a company is newly discovered or changed. Legacy rows without explicit attribution SHALL remain unknown and SHALL NOT be backfilled or inferred.

#### Scenario: Company write commits
- **WHEN** managed invocation X commits a company through its `gold.company` stage job
- **THEN** one durable attribution links X, that exact stage job, and the company, and the bounded results API returns that company with its current Gold fields.

#### Scenario: Company write rolls back or predates managed tracking
- **WHEN** the company write rolls back, or the write occurred before explicit invocation attribution existed
- **THEN** no invocation/company result is reported for that write, and the system does not infer membership from timestamps or aggregate counters.

### Requirement: Durable history and safe event logs
Administrator history SHALL support bounded pagination and deterministic newest-first ordering. Detail and event APIs SHALL identify the invocation, requester, lifecycle timestamps, final result, stage/source records, dependency skip reasons, safe errors, and ordered event IDs. Events SHALL be paginated by a monotonically ordered cursor scoped to the invocation. Returned logs SHALL exclude credentials, proof/session values, DSNs, payloads, and raw exception/database text.

#### Scenario: Invocation isolation
- **WHEN** an administrator requests detail/events for invocation X
- **THEN** only explicitly linked X records are returned and history for invocation Y cannot bleed into that view.

#### Scenario: Tracking unavailable
- **WHEN** durable managed tracking cannot be persisted before a stage starts
- **THEN** the worker does not start that stage and the invocation is not falsely reported as completed.

### Requirement: Crash and commit uncertainty remain visible
Queued work SHALL survive restart. Started invocations SHALL not be automatically replayed after uncertain execution or worker loss. A stale heartbeat SHALL be displayed as stale tracking rather than proof of success/failure. A trusted operator SHALL reconcile interrupted work only after confirming the previous executor has stopped, retaining completed stages and marking unfinished work interrupted without rewriting successful rows. A later manual rerun SHALL use a new invocation ID.

#### Scenario: Worker disappears mid-stage
- **WHEN** an invocation remains running with stale worker heartbeat
- **THEN** it remains exclusive and visibly stale until safe reconciliation, rather than another worker automatically starting it again.

#### Scenario: Operator recovery
- **WHEN** the prior executor is confirmed stopped and the operator reconciles invocation X
- **THEN** X becomes interrupted with a safe recovery event, previously completed rows remain intact, and a new manual invocation can be accepted.

### Requirement: Shared standards and explicit placement
Implementation SHALL comply with the authoritative [foundation standards](../../../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) and this change's exact design inventory. New application ports SHALL use `application/protocols`; existing persistence conventions SHALL be preserved. Domain SHALL not import application/read-model/HTTP/persistence types. New Python value types SHALL be frozen dataclasses and new application use cases SHALL expose `execute(Request) -> Response`. Pyright adoption remains deferred. Schema changes SHALL regenerate the shared offline OpenAPI/TypeScript artifacts and pass the drift gate.

#### Scenario: Review implementation placement
- **WHEN** this change adds a service, type, query projection, repository, row model, or browser feature
- **THEN** its named file and dependency direction follow the exact design inventory and shared conventions without duplicate session/database/tooling definitions.
