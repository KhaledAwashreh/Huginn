## Context

See [proposal.md](proposal.md). Current implementation inspected at `.worktrees/simple-matchmaking` `ca2ddd9`: `elt/__main__.py`, `elt/stage_runner.py`, `elt/materialization.py`, `elt/ingestion/service.py`, `ops/job_runs.py`, `ops/postgres_job_run_writer.py`, `db/schema/ops.sql`, ADR0014, and management authentication/current-session types.

`ops.job_runs` stores independent source/stage records with no parent invocation. Its source ID also identifies Bronze run lineage. Current stage-runner tracking is best-effort and may lose bookkeeping while work continues. Full ELT comprises HN/YC aggregate ingestion plus independent EU-Startups discovery, shared resolution, manual-review queuing, and Gold writes. OpenCorporates is only in the separate ingestion path. Critically, the aggregate ingestion stage returns failed-source count, whereas other stages return row counts. A new API must not relabel this value as ingestion rows.

Primary contains a user-owned edit to `src/huginn/ops/postgres_job_run_writer.py`; do not copy, discard, or absorb it. Apply from the inspected feature base or its actual merged successor and adapt narrowly to current source, preserving unrelated worktrees and change artifacts.

## Goals / Non-Goals

**Goals:** A manually triggered durable run, server-authorized operations, invocation-specific source/stage/event history, recoverable visible failures, and preserved ELT policy.

**Non-Goals:** Celery/Redis/Prefect, scheduler replacement, arbitrary job framework, new scrapers, per-stage rerun/cancellation, matching/scoring/digests within the pipeline, automatic failed-run replay, or a searchable raw-log platform. Existing CLI operational behavior remains supported with the shared execution guard, which a separate `admin-matchmaking-execution` change may extend additively to serialize a distinct matchmaking operation.

## Decisions

### 1. Roles belong to Account; operation service is a sibling

Add AccountRole user/admin as a domain value object and constrained column `operational.accounts.role DEFAULT 'user'`. Backfill no administrators automatically. Trusted existing account-admin CLI gets explicit role assignment with operator confirmation; no HTTP role-edit API. Public provisioning defaults user and rejects role input. Add authorization dependency loading current role from authoritative Account on every request. Extend foundation current-session response with role here, not by duplicating session ownership in the frontend.

Keep server orchestration in sibling `huginn.pipeline_control`, outside user configuration and management business CRUD. FastAPI management presentation mounts pipeline routers through composition; auth adapter passes an immutable administrator principal to application requests. The domain does not depend on FastAPI or management application types. Pipeline application composes existing ELT through a port; it does not duplicate parsers/repositories or relocate ELT.

The exact inventory below defines every new production type/file. Application ports use `application/protocols`; persistence ports adopt the existing management `persistence/contracts` convention. Query projections are returned by application query ports, not domain repositories.

No umbrella file mixes domain entities, requests, read models, repositories, or services. Use explicit `Service.execute(Request) -> Response` for new application use cases and frozen value types/Protocol contracts following existing architecture. Existing ELT libraries remain DB-free at construction and use bounded synchronous thread pools; no asyncio rewrite.

### 2. PostgreSQL queue and invocation model

Use the existing PostgreSQL database, no extra infrastructure. Add `ops.pipeline_invocations`: UUID id, requester_account_id, request_id, state (queued/running/succeeded/failed/interrupted), requested_at, started_at, finished_at, immutable pipeline plan JSON, worker_id, heartbeat_at, safe_error_code. Unique `(requester_account_id,request_id)` makes trigger retries idempotent. A partial unique index on a constant where state in queued/running ensures one managed active invocation globally. Guard enqueue/idempotency checks with one transaction and a short transaction advisory lock in the distinct `pipeline-trigger` lock namespace; resolve same-request idempotency before checking the active-run conflict. This is not the long-lived execution lock. The HTTP trigger MUST NOT acquire or wait on the shared `shared-execution` session advisory lock, so an active pipeline or matcher does not hold the request open; a conflict returns 409 with active invocation ID to admins only, while the accepted queued work waits for execution admission. The trigger lock and execution lock use distinct PostgreSQL advisory lock tags/namespaces.

Add optional `invocation_id`, `parent_job_run_id`, and execution kind (`stage` or `source`) to linked job records (nullable on historical rows) with FKs/indexes; JobRun types/writer contract carry optional lineage. Stage rows retain existing job_run IDs, names/statuses; child ingestion writers get the specific parent stage ID explicitly. Bronze.run_id is unchanged. No backfill guesses invocation from time. Persist planned stage descriptors on acceptance so pending stage detail exists without synthetic running job rows.

Add `ops.pipeline_invocation_events`: per-invocation monotonic sequence, timestamp, allowlisted event kind, stage/source references, safe code/message, typed bounded metrics. Store only structured operational messages, never captured stdout or raw exceptions. Event uniqueness ensures retries don't duplicate transitions. Durable worker ownership/start/finalization is independent of HTTP process lifetime. Tracking, lifecycle, and source lineage are invocation-specific even when legacy job bookkeeping remains best-effort for unmanaged runs.

Add a singleton `ops.pipeline_execution_guard` row with owner UUID, execution UUID, pipeline invocation ID, host/supervisor/executor process identity, acquired/released timestamps, and active flag. Both supported full CLI and managed worker MUST atomically claim this durable guard before starting a child executor, alongside the long-lived session advisory lock in the distinct `shared-execution` namespace. A later `admin-matchmaking-execution` change owns an additive migration that introduces a constrained `resource_kind` and optional matching-run reference, then claims the same guard and `shared-execution` advisory resource for its distinct matcher invocation. Pipeline callers continue to claim only `resource_kind=pipeline`; they do not import, invoke, or record matcher work. This shared serialization means an active matcher causes a pipeline worker to leave queued work waiting and a supported full CLI to exit busy, while an active pipeline similarly blocks matcher admission. The trigger admission lock remains independent and short-lived; no HTTP trigger takes the session execution lock. Active guard is not a renewable lease: it never expires automatically and remains blocking after lock/connection/process loss. Clearing requires matching owner identity and confirmed executor termination; no TOCTOU check followed by an unguarded new executor. All callers treat unavailable guard storage as unavailable execution, never as permission to proceed.

### 3. Exact stage plan and metrics

| Stage | Dependencies | Group |
| --- | --- | --- |
| `ingestion` | None | Source/Bronze; child `hn`, `yc` |
| `ingestion.eu_startups` | None | Source/Bronze; child `eu_startups` |
| `silver.hn_staging` | `ingestion` | Silver |
| `silver.yc_staging` | `ingestion` | Silver |
| `silver.eu_startups_staging` | `ingestion.eu_startups` | Silver |
| `silver.signal_resolution` | all three staging stages | Silver |
| `silver.manual_review` | `silver.signal_resolution` | Silver; queueing only |
| `gold.company` | `silver.signal_resolution` | Gold |
| `gold.company_signal` | `silver.signal_resolution`, `gold.company` | Gold |

Snapshot descriptors produced from the existing stage builder, retaining ordered names/dependencies and validating this known supported graph. Expose plan state pending before job starts; job state running/succeeded/failed/skipped afterward. Interrupted worker cases expose an additional execution interruption marker without pretending pending stages were dependency-skipped or rewriting job CHECK values.

Metrics are `{kind, unit, value}` with nullable values until measured. Aggregate ingestion kind=`failed_sources`, unit=`sources`; normal materialization/source writes use kind=`rows_written`, unit=`rows` only when truly returned by that unit. Optional already-available rejection/exclusion/read counters retain separate kinds; do not invent them from row deltas or add global count queries for apparent progress. No percentage denominator is supplied initially. Preserve current stage dependency policy, source isolation, retry rules, and existing code paths. A failure in manual-review queuing does not block Gold, because Gold depends on resolution, not that queueing stage.

### 4. HTTP and error contracts

| Endpoint | Contract |
| --- | --- |
| `POST /api/v1/admin/pipeline/invocations` | Strict `{request_id: UUID}`; administrator session plus CSRF;202 `{id,status,requested_at}` and Location header; same requester/request_id returns existing receipt, distinct active conflict 409 with safe active_invocation_id |
| `GET /api/v1/admin/pipeline/invocations` | limit1..100, offset>=0, optional validated state; `{items,limit,offset,has_more}` ordered requested_at DESC,id DESC |
| `GET /api/v1/admin/pipeline/invocations/{id}` | Invocation metadata, tracking freshness, ordered stage plan/executions, exact source-child records, safe metrics, final outcome; 404 for nonexistent |
| `GET /api/v1/admin/pipeline/invocations/{id}/events` | after_sequence>=0, limit1..100; `{items,next_after_sequence,has_more}` ordered sequence ASC |
| `GET /api/v1/admin/pipeline/invocations/{id}/companies` | limit1..100, offset>=0; `{tracking_state,items,total_count,limit,offset,has_more}` with a bounded page of current Gold company records successfully written by this invocation's `gold.company` job and deterministic company-ID ordering. Each item allowlists only `id`, `name`, `domain`, `business_sector`, `country`, `company_scale`, `company_status`, and `stage_job_run_id`; exclude Gold contact fields and `notes` |

Current server envelope is preserved for generic 401/403/404/422/429/500 and native sanitized 422 detail. 409 active-run response is a documented specialized safe error detail extension under existing error envelope, not raw exception text. Body unknown keys and invalid UUID/filter/cursor fields rejected. GETs require administrator but no CSRF. All private operational responses, including company results, use no-store. Company-result pagination is bounded to at most 100 rows and reads only attribution rows for the requested invocation; missing/legacy associations return an empty page, never inferred membership. Trigger rate limit defaults10 per administrator per hour with 429/Retry-After and counts distinct requests, not harmless same-key receipt lookup.

### 5. Execution guard, worker and recovery

Dedicated synchronous worker CLI polls committed queued work with bounded idle wait and graceful signal handling. It claims a row using `FOR UPDATE SKIP LOCKED`, obtains a session advisory lock on a dedicated connection, atomically claims the durable execution guard, persists running/worker identity/start event, and commits before spawning a trusted supervised executor child process in its own process group. Child uses existing ELT stage runner with invocation-aware writer context; public requests never control executable/arguments. Persist/process-start handshake guarantees an active durable guard exists even if the parent dies around spawn, and the child reports its exact process identity before stage execution. Full-pipeline CLI uses the same durable guard/advisory protocol and supervised child, with nullable invocation ID for legacy operation. If either gate is busy it exits nonzero with safe message; a worker leaves queued work queued and retries later. Other ingestion-only/enrichment CLIs are not made managed full invocations; document that operators must not run them concurrently with this shared pipeline because they are outside the guard's initial scope.

A heartbeat loop on a separate bounded supervisor thread records liveness every 15 seconds; detail flags stale after60 seconds without declaring completion. Poll/DB/network calls have bounded timeouts. Durable pre-stage tracking is required for managed execution: failure before starting a stage prevents its work; after work started, lost tracking/guard connection causes the supervisor to terminate the entire executor process group, wait a bounded 5 seconds, escalate to kill, and reap/verify all owned executor processes before conditionally recording interrupted/releasing the durable gate. The gate remains active throughout cleanup and whenever termination/settlement cannot be proven. External requests already sent may finish remotely; no overlapping local executor is admitted while old local fetch/write threads remain. Killing can interrupt a database transaction; PostgreSQL handles its rollback, and stage-level prior committed writes remain. Do not hold row transactions open across external calls. Supervisor failure leaves a durable blocker and possibly an orphan child for explicit operator cleanup, never automatic gate expiry.

After a worker dies, restart never replays running work. The active invocation and durable execution gate block new managed/CLI execution. Trusted `pipeline reconcile --invocation-id ... --executor-stopped` command requires operator evidence that the exact owning supervisor/executor process group has ended (including host/process-start identity to avoid PID reuse), and obtains the resource lock; it validates owner/state, records interruption, preserves completed rows, marks started unfinished execution as interrupted in the invocation projection, and atomically clears matching durable gate/active-row exclusivity. For interrupted standalone full CLI, the equivalent trusted command takes execution ID and records gate recovery without fabricating an invocation. It MUST NOT clear a gate on heartbeat age or advisory-lock availability alone. Pending stages become not-executed due to interruption, distinct from dependency skip. Queue state is safe to claim after restart because no stage started. Unknown trigger COMMIT is reconciled using requester/request_id; unknown worker final COMMIT is resolved by re-reading state, never running stages again. Full rerun is a deliberate new invocation, no reset or delete.

### 6. Gold company attribution without result snapshots

Current `CompanyWriter.write_all()` owns the complete company batch transaction and enters `self._repository` for that batch. Preserve that whole-batch scope and repository cursor: `elt/materialization.py` must pass the managed invocation/stage context into `CompanyWriter`; the repository's existing `upsert_company()` operation returns the persisted company ID with `RETURNING id`, and the managed attribution insert uses that ID through the same open repository/cursor. Do not open a second connection, commit per company, or move attribution outside `CompanyWriter.write_all()`. A successful batch commit makes its Gold writes and attribution rows visible together; if the batch rolls back, all of that batch's Gold writes and attribution rows disappear together. Prior writes committed by earlier pipeline stages remain intact, and the invocation may still finish failed if this batch fails.

Store attribution in narrow durable `ops.pipeline_company_results(invocation_id, company_id, stage_job_run_id)` with a uniqueness constraint on `(invocation_id, company_id)`. Validate that the supplied managed write context is specifically the `gold.company` stage and that its job run belongs to the same invocation. Enforce the invocation/job pair with a composite foreign key `(invocation_id, stage_job_run_id)` to the linked `ops.job_runs(invocation_id,id)` pair (add the matching unique key if needed), rather than trusting a job ID alone. Add an explicit company-results tracking state to invocations: new managed invocations created after this capability is deployed are marked tracked, while the additive migration leaves existing invocations unknown legacy. This lets the API distinguish known zero results from unavailable historical attribution without guessing from timestamps. Unmanaged legacy Gold writes do not fabricate an invocation association. The table is operational attribution only: it stores no company-field snapshot and no claim that a company was newly discovered or changed. The API joins these IDs to the current Gold company fields, so later edits may change displayed fields while invocation membership remains the durable fact. Summary and row labels say “processed” or “written by this run,” never “new” or “changed.”

### 7. Tracking integration without policy replay

Managed executor provides stable stage context and wraps existing JobRun writer so both stage runner and nested ingestion services explicitly inherit invocation/parent IDs. No ContextVar-only magic or timestamp grouping; pass context/writer in builder/service injection. Legacy CLI calls without context retain nullable lineage and existing status semantics. Managed mode's tracking strictness is new operational behavior, not a rewrite of source/parser failure policy. Add explicit transaction tests showing source lineage survives status updates and Bronze linkage remains source-job ID. Safe allowlist event mapper translates exceptions to stable error codes; detailed traces stay local protected logs with normal existing security constraints, never exported to console.

## Risks / Trade-offs

- [PostgreSQL outage while work runs] → Stop subsequent work, preserve uncertain running record, no automatic replay, explicit stopped-executor reconciliation.
- [One-active queue blocks after crash] → Deliberate safety tradeoff; visible stale state and tested operator recovery runbook.
- [Best-effort legacy tracking] → Strict managed tracking boundary, nullable backward-compatible lineage, no fake historical invocations.
- [Pipeline/CLI interference] → Shared guard for full entrypoint, documented exclusion of concurrent standalone ingestion/enrichment commands.
- [Metric mismatch] → Explicit metric kind/unit and no misleading aggregate row count/percentage.

## Migration Plan

`db/schema/ops.sql` remains the base job-run bootstrap: it creates `ops.job_runs` without control-plane foreign keys or other pipeline-control DDL. Do not add FK-dependent control tables or job-lineage columns to that early file. Apply the existing base bootstrap in its documented dependency order through both `gold.sql` and `operational.sql`; then apply `operational-account-role.sql`, followed by `ops-pipeline-control.sql`. The control migration creates invocations/events/guard/company attribution and ALTERs the already-created `ops.job_runs` with nullable lineage columns and their FKs, including references to invocations, self-linked parent jobs, and Gold company rows. This same post-bootstrap ordering applies to fresh databases and existing databases after their prerequisite schemas are present. `ops-pipeline-control.sql` must never run before `gold.sql` and `operational.sql`.

Update `db/schema/README.md` and `docs/management-foundation.md` with the post-bootstrap migration order and commands. In `tests/postgres_harness.py`, retain `BASE_SCHEMA_FILES` for the existing seven-file dependency-ordered bootstrap and append the two post-bootstrap migrations only in the full fresh `SCHEMA_FILES` sequence. Keep separate scenarios in `tests/ops/test_pipeline_control_schema_integration.py`: the fresh-bootstrap scenario starts empty and applies the full ordered sequence; the legacy-upgrade scenario applies only `BASE_SCHEMA_FILES`, seeds legacy job/account/company rows, then applies the two additive migrations and verifies rows/statuses survive and no historical invocation or company links are fabricated. Do not fold the legacy-upgrade check into the fresh-bootstrap fixture or place FK-dependent control DDL in `ops.sql`.

All DDL remains operator-applied; no application boot DDL. Deploy role-aware auth/API first, assign one admin explicitly, then deploy worker/execution guard and enable trigger. Stop existing full-pipeline cron during cutover until its CLI uses the guard. Rollback disables trigger and stops worker, preserving history; do not downgrade while an invocation is executing. Document manual worker start, SMTP worker separation, reconciliation, queue waiting, and dedicated DB integration fixtures. No Jira update, push, or PR is implied.

## Shared standards dependency

The authoritative [foundation implementation standards](../web-ui-foundation/design.md#6-shared-implementation-standards-authoritative-for-all-five-changes) govern this change: exact Node/npm/dependency locks, strict TypeScript, naming, offline schema drift, lint/format/test/CI/hook gates, WCAG 2.2 AA target, and Python layer placement. Consume shared components and transport; do not introduce divergent tooling or duplicate session/database ports. The inventories below define the new production files/types for this feature. Package `__init__.py` markers are empty, not public re-export umbrellas. Test files mirror these use cases and add the behavior scenarios already specified in this design.

## Exact pipeline server inventory

Paths relative to `src/huginn/pipeline_control/`. Immutable request/read-model values are frozen dataclasses; HTTP and row boundary validation models remain separate. Domain-only repository ports do not return application projections; `InvocationReader` owns projection queries. Worker claims/process identity are application read models, durable guard rows are persistence models.

| Exact path | Named types / exports |
| --- | --- |
| `domain/entities/pipeline_invocation.py` | PipelineInvocation |
| `domain/value_objects/invocation_state.py` | InvocationState |
| `domain/value_objects/stage_plan.py` | StagePlan |
| `domain/value_objects/stage_descriptor.py` | StageDescriptor |
| `domain/value_objects/requester.py` | Requester |
| `domain/value_objects/pipeline_event.py` | PipelineEvent |
| `domain/value_objects/metric.py` | Metric |
| `domain/value_objects/execution_owner.py` | ExecutionOwner |
| `domain/errors/invocation.py` | ActiveInvocationConflictError, InvalidInvocationTransitionError |
| `application/errors/invocation.py` | InvocationNotFoundError; safe missing-invocation query outcome |
| `application/errors/trigger.py` | TriggerRateLimitError; distinct-request throttle outcome with retry_after_seconds |
| `application/errors/execution.py` | ExecutionUnavailableError, TrackingUncertainError, ExecutorTerminationUnprovenError |
| `application/constants/execution_policy.py` | HEARTBEAT_SECONDS, STALE_AFTER_SECONDS, TERMINATION_GRACE_SECONDS, TRIGGER_HOURLY_LIMIT |
| `domain/constants/event_kinds.py` | ALLOWED_EVENT_KINDS |
| `application/protocols/pipeline_executor.py` | PipelineExecutor Protocol |
| `application/protocols/invocation_reader.py` | InvocationReader Protocol; application projections |
| `application/protocols/invocation_company_reader.py` | InvocationCompanyReader Protocol |
| `application/protocols/executor_supervisor.py` | ExecutorSupervisor Protocol |
| `application/protocols/execution_guard.py` | ExecutionGuard Protocol |
| `application/read_models/invocation_summary.py` | InvocationSummary |
| `application/read_models/invocation_detail.py` | InvocationDetail |
| `application/read_models/stage_execution.py` | StageExecution |
| `application/read_models/source_execution.py` | SourceExecution |
| `application/read_models/event_entry.py` | EventEntry |
| `application/read_models/invocation_company_result.py` | InvocationCompanyResult; current company fields plus attribution metadata, not a snapshot |
| `application/read_models/worker_claim.py` | WorkerClaim |
| `application/read_models/executor_identity.py` | ExecutorIdentity |
| `application/read_models/tracking_context.py` | TrackingContext |
| `application/requests/trigger_invocation_request.py` | TriggerInvocationRequest |
| `application/responses/trigger_invocation_response.py` | TriggerInvocationResponse |
| `application/services/trigger_invocation_service.py` | TriggerInvocationService.execute(TriggerInvocationRequest) -> TriggerInvocationResponse |
| `application/requests/list_invocations_request.py` | ListInvocationsRequest |
| `application/responses/list_invocations_response.py` | ListInvocationsResponse |
| `application/services/list_invocations_service.py` | ListInvocationsService.execute(ListInvocationsRequest) -> ListInvocationsResponse |
| `application/requests/get_invocation_request.py` | GetInvocationRequest |
| `application/responses/get_invocation_response.py` | GetInvocationResponse |
| `application/services/get_invocation_service.py` | GetInvocationService.execute(GetInvocationRequest) -> GetInvocationResponse |
| `application/requests/list_events_request.py` | ListEventsRequest |
| `application/responses/list_events_response.py` | ListEventsResponse |
| `application/services/list_events_service.py` | ListEventsService.execute(ListEventsRequest) -> ListEventsResponse |
| `application/requests/list_invocation_companies_request.py` | ListInvocationCompaniesRequest |
| `application/responses/list_invocation_companies_response.py` | ListInvocationCompaniesResponse |
| `application/services/list_invocation_companies_service.py` | ListInvocationCompaniesService.execute(ListInvocationCompaniesRequest) -> ListInvocationCompaniesResponse |
| `application/requests/reconcile_invocation_request.py` | ReconcileInvocationRequest |
| `application/responses/reconcile_invocation_response.py` | ReconcileInvocationResponse |
| `application/services/reconcile_invocation_service.py` | ReconcileInvocationService.execute(ReconcileInvocationRequest) -> ReconcileInvocationResponse |
| `application/requests/reconcile_execution_request.py` | ReconcileExecutionRequest |
| `application/responses/reconcile_execution_response.py` | ReconcileExecutionResponse |
| `application/services/reconcile_execution_service.py` | ReconcileExecutionService.execute(ReconcileExecutionRequest) -> ReconcileExecutionResponse |
| `application/requests/run_queued_invocation_request.py` | RunQueuedInvocationRequest |
| `application/responses/run_queued_invocation_response.py` | RunQueuedInvocationResponse |
| `application/services/run_queued_invocation_service.py` | RunQueuedInvocationService.execute(RunQueuedInvocationRequest) -> RunQueuedInvocationResponse |
| `persistence/contracts/repositories/invocation.py` | InvocationRepository Protocol; domain entities/value objects or scalar IDs/owner data only; no row models escape adapter |
| `persistence/repositories/invocation.py` | PostgresInvocationRepository |
| `persistence/row_models/invocation.py` | InvocationRow |
| `persistence/contracts/repositories/invocation_event.py` | InvocationEventRepository Protocol; domain entities/value objects or scalar IDs/owner data only; no row models escape adapter |
| `persistence/repositories/invocation_event.py` | PostgresInvocationEventRepository |
| `persistence/row_models/invocation_event.py` | InvocationEventRow |
| `persistence/contracts/repositories/invocation_company_result.py` | InvocationCompanyResultRepository Protocol; domain values/scalar IDs only |
| `persistence/repositories/invocation_company_result.py` | PostgresInvocationCompanyResultRepository |
| `persistence/row_models/invocation_company_result.py` | InvocationCompanyResultRow |
| `persistence/contracts/repositories/job_linkage.py` | JobLinkageRepository Protocol; domain entities/value objects or scalar IDs/owner data only; no row models escape adapter |
| `persistence/repositories/job_linkage.py` | PostgresJobLinkageRepository |
| `persistence/row_models/job_linkage.py` | JobLinkageRow |
| `persistence/contracts/repositories/execution_guard.py` | ExecutionGuardRepository Protocol; domain entities/value objects or scalar IDs/owner data only; no row models escape adapter |
| `persistence/repositories/execution_guard.py` | PostgresExecutionGuardRepository |
| `persistence/row_models/execution_guard.py` | ExecutionGuardRow |
| `persistence/contracts/repositories/trigger_throttle.py` | TriggerThrottleRepository Protocol; domain entities/value objects or scalar IDs/owner data only; no row models escape adapter |
| `persistence/repositories/trigger_throttle.py` | PostgresTriggerThrottleRepository |
| `persistence/row_models/trigger_throttle.py` | TriggerThrottleRow |
| `persistence/contracts/unit_of_work.py` | PipelineUnitOfWork Protocol; reuse management DatabaseSession |
| `persistence/database/unit_of_work.py` | PostgresPipelineUnitOfWork; same synchronous database client |
| `persistence/queries/invocation_reader.py` | PostgresInvocationReader; maps invocation/stage/source/event rows into application read models |
| `persistence/queries/invocation_company_reader.py` | PostgresInvocationCompanyReader implements InvocationCompanyReader; bounded invocation-scoped join to current allowed Gold fields and attribution rows |
| `persistence/constants/schema.py` | PIPELINE_INVOCATIONS_TABLE, PIPELINE_EVENTS_TABLE, PIPELINE_COMPANY_RESULTS_TABLE, EXECUTION_GUARD_TABLE |
| `infrastructure/elt_pipeline_executor.py` | EltPipelineExecutor implements PipelineExecutor |
| `infrastructure/invocation_job_run_writer.py` | InvocationJobRunWriter; explicit TrackingContext |
| `infrastructure/invocation_company_result_writer.py` | InvocationCompanyResultWriter; writes attribution in the Gold company transaction |
| `infrastructure/process_supervisor.py` | ProcessExecutorSupervisor implements ExecutorSupervisor |
| `infrastructure/postgres_execution_guard.py` | PostgresExecutionGuard implements ExecutionGuard |
| `infrastructure/safe_event_mapper.py` | map_safe_event |
| `presentation/api/requests/trigger_invocation.py` | TriggerInvocationRequest HTTP model |
| `presentation/api/requests/list_invocations.py` | ListInvocationsQuery |
| `presentation/api/requests/list_events.py` | ListEventsQuery |
| `presentation/api/requests/list_invocation_companies.py` | ListInvocationCompaniesQuery |
| `presentation/api/responses/invocation_receipt.py` | InvocationReceiptResponse |
| `presentation/api/responses/invocation_history.py` | InvocationHistoryResponse |
| `presentation/api/responses/invocation_detail.py` | InvocationDetailResponse |
| `presentation/api/responses/stage_execution.py` | StageExecutionResponse |
| `presentation/api/responses/source_execution.py` | SourceExecutionResponse |
| `presentation/api/responses/event_page.py` | EventPageResponse |
| `presentation/api/responses/event_entry.py` | EventEntryResponse |
| `presentation/api/responses/invocation_companies.py` | InvocationCompaniesResponse; tracking_state=`tracked|unknown_legacy`, items, total_count, limit, offset, has_more |
| `presentation/api/responses/invocation_company_result.py` | InvocationCompanyResultResponse; allowlisted id/name/domain/business_sector/country/company_scale/company_status/stage_job_run_id |
| `presentation/api/responses/metric.py` | MetricResponse |
| `presentation/api/errors/active_invocation.py` | ActiveInvocationErrorResponse; existing error envelope extension |
| `presentation/api/routers/invocations.py` | pipeline invocation routes |
| `presentation/cli/worker.py` | main; dedicated synchronous worker |
| `presentation/cli/reconcile.py` | main; invocation/execution stopped-owner reconciliation |
| `presentation/cli/executor.py` | main; trusted supervised child handshake |
| `bootstrap.py` | create_pipeline_services |
| `config.py` | PipelineControlConfig |
| `__main__.py` | main; pipeline CLI dispatcher |

Narrow existing management edits: `domain/value_objects/account_role.py` adds `AccountRole`; `domain/entities/account.py` extends `Account`; `domain/value_objects/common.py` extends `Principal` with role; repository account/session selection and authentication snapshot carry authoritative role; `presentation/api/dependencies/administrator.py` adds `require_administrator` using existing authenticated session; `application/requests/assign_account_role_request.py`, `application/responses/assign_account_role_response.py`, `application/services/assign_account_role_service.py` add `AssignAccountRoleRequest`, `AssignAccountRoleResponse`, `AssignAccountRoleService.execute`; existing account-admin CLI invokes that service with confirmation. Foundation application/HTTP current-session responses gain role here. Existing `management/persistence/database/client.py` adds an optional positive statement_timeout_ms connection setting, defaulting to unchanged management behavior; pipeline HTTP/worker/reader connections opt into 2000ms bounds. Existing `management/app.py` mounts pipeline router and composition; no replacement auth stack.

Extend existing `ops/job_runs.py` (`JobRun`, `JobRunWriterPort` lineage), `ops/postgres_job_run_writer.py` (`PostgresJobRunWriter` conditional lineage preservation), `elt/stage_runner.py` (explicit writer/context injection and strict managed boundary), `elt/materialization.py` (pass managed `TrackingContext` through the materialization builder into `CompanyWriter`), `elt/ingestion/service.py` (child parent injection), `elt/gold/company.py` (`CompanyWriter.write_all()` whole-batch scope), `elt/gold/ports.py` (`CompanyRepositoryPort.upsert_company()` returns UUID), `elt/gold/repositories/company_repository.py` (both `build_upsert_query()` branches add `RETURNING id`; `upsert_company()` returns that ID and performs attribution through the same repository cursor), and `elt/__main__.py` (shared supervisor/guard full CLI). Preserve `db/schema/ops.sql` unchanged as the base job-runs bootstrap; put control DDL and ALTERs only in the post-base `db/schema/ops-pipeline-control.sql` migration. Additive role DDL stays in `db/schema/operational-account-role.sql`, also after `operational.sql`. Update only the schema-order documentation and fixture inventory listed below. Keep DB-free core and existing source/dependency/retry policy; preserve all existing guard, supervisor, recovery, and tracking contracts.

| Narrow existing integration | Required update |
| --- | --- |
| `db/schema/README.md` | Keep the base bootstrap order; document role/control migrations after the seven base files, with `operational-account-role.sql` before `ops-pipeline-control.sql` |
| `docs/management-foundation.md` | Update local fresh-bootstrap commands and explain additive migrations are post-bootstrap, never startup DDL |
| `tests/postgres_harness.py` | Keep seven-file `BASE_SCHEMA_FILES`; append role/control migrations to fresh `SCHEMA_FILES` only after all base files |
| `tests/ops/test_pipeline_control_schema_integration.py` | Use the full ordered sequence for empty-database fresh bootstrap and only `BASE_SCHEMA_FILES` before additive migrations in legacy-upgrade coverage |
| `src/huginn/elt/gold/ports.py` | Update `CompanyRepositoryPort.upsert_company()` return contract to persisted UUID |
| `tests/elt/gold/test_company_repository.py` | Update INSERT and UPDATE SQL-shape expectations for `RETURNING id` |
| `tests/elt/gold/test_company.py` | Update in-memory repository fake to return the persisted company UUID |
| `tests/elt/gold/test_company_repository_integration.py` | Verify both upsert forms return the exact persisted UUID |

The two new control migrations add invocation/event/guard/throttle/linkage/company-attribution/role constraints without changing legacy job CHECK states. The control migration adds the explicit tracked/unknown-legacy state, composite invocation/job linkage, and attribution table without backfilling guessed historical links. Reuse existing parameterized database and error contracts; no duplicate connection abstractions.
