## Context

See [proposal.md](proposal.md). Inspected the actual implementation in `.worktrees/user-configuration-workspace`: matcher `application/services/{matchmaking_service,batch_matchmaking_service}.py`, `bootstrap.py`, `presentation/cli.py`, SQL unit of work/repositories, management session/CSRF composition, and current configuration frontend. The existing batch accepts explicit UUIDs, runs users serially, and returns results after execution; it neither enumerates all users nor persists run history/progress. The single-user service already owns criteria compilation, repeatable-read transactions, known retry policy, and unknown-commit classification. Operational Match stores no originating strategy/run or historical evidence.

The planned [pipeline server](../pipeline-control-and-history/design.md) supplies roles, authoritative administrator dependency, PostgreSQL durable guard, and supervised execution. Its guard must be deployed first. The approved user-facing Matches feature is a separate read-only consumer. Architecture's earlier dashboard/RBAC deferrals are explicitly advanced by these approved changes; scoring/delivery/evidence remain deferred.

## Goals / Non-Goals

**Goals:** Browser-triggered existing service execution, fixed targets/window, durable per-user acknowledgement, honest progress, and one execution boundary with collection.

**Non-Goals:** A second evaluator, generic job builder, scheduler, automatic collection-to-matching chain, parallel user evaluation, cancellation/resume/replay UI, status/notes edits, scoring/ranking, historical why-matched explanations, new infrastructure, or an administrator CRUD suite.

## Decisions

### 1. Thin control boundary and dependencies

Use sibling `huginn.matchmaking_control`, composed into the existing management API. Presentation adapts the existing authoritative administrator session into an immutable control Requester. Domain remains independent of FastAPI/management/matcher application models. Control services use Protocols and the existing synchronous database client; only the infrastructure adapter imports the matcher API and maps its results. Keep the existing matcher database/UoW boundary unchanged.

Expose a narrow `build_service(config)` in existing matcher bootstrap, preserving `build_batch_service` and its response shape. The supervised control loop calls `MatchmakingService.execute(MatchmakingRequest)` once per captured user. This reuses the actual matcher and exposes progress between user transactions without adding callbacks/evaluation code to its domain. Alternative: calling the existing batch once would hide intermediate durable progress; duplicating its evaluator would create competing policy.

Dependency order: merged foundation/lifecycle + user configuration + existing matchmaking -> `pipeline-control-and-history` -> this change. `admin-pipeline-console` can ship alongside this change after the pipeline server; it is not a matcher dependency. `user-matches-view` depends on this change's deployed result tables for contextual empty states, but ordinary users receive no administrator permissions.

### 2. Immutable trigger contract

`POST /api/v1/admin/matchmaking/runs` body is a strict discriminated target (`{kind:"user",user_id:UUID}` or `{kind:"all_eligible"}`), `request_id:UUID`, required offset-aware `cutoff`, and optional offset-aware `as_of`. Normalize timestamps to UTC; resolve omitted as_of once at acceptance and reject cutoff>as_of or future as_of. UI presets last 7/30/90 days and custom dates; proposed MVP default is 30 days, visibly editable, with timezone/UTC preview. These are window presets, not a relaxation of the existing signal requirement.

Store canonical submitted payload separately from resolved as_of/target IDs. Under a short admission transaction/advisory lock in the `matchmaking-trigger` namespace, same requester/request_id lookup happens first: identical canonical input returns existing receipt even if targets changed or a run finished; different input returns409 request_identity_conflict. The admission key is distinct from both the pipeline-trigger admission key and the long-lived shared-execution key; submitting/looking up a queued run never waits for a running executor's session lock. An omitted as_of remains omitted in the canonical input, not replaced with a new clock value on retry. Accept one managed queued/running matching run via partial unique index, returning409 active_matching_run_id for distinct submissions. Same-key lookup is not a new throttle charge; distinct attempts default to10/admin/hour using the pipeline throttle convention with a separate action namespace.

All-eligible enumerates users joined to active accounts with EXISTS active strategy, without validating each ICP at trigger time. Capture sorted unique IDs in the same acceptance transaction as the run; no LIMIT100 truncation. A single target must exist and have an active account at acceptance (404 missing,422 disabled); allow zero strategies and report evaluated0 later. All-eligible with no targets returns422 no_eligible_users. The service rechecks each target/account/configuration in its existing transaction. Target membership/window are fixed; configuration itself is current at evaluation, not snapshotted at enqueue.

Admin user-search GET is bounded, literal substring name/username search and exact UUID lookup when search is a UUID; return id,username,first_name,last_name,has_active_strategies for active accounts only. No email/recovery/contact/secrets/criteria. Preview eligible count is current information; accepted receipt count is authoritative. TargetUserQuery returns Page[TargetUser] and provides eligible_count(); the application reads them in one read snapshot and returns ListTargetUsersResponse(page,total_eligible_count), not a persistence import of an application response class.

### 3. Durable run and user results

Add `ops.matchmaking_runs`: id,requester_account_id,request_id,canonical_request JSON,target_kind,cutoff,as_of,state,requested_at,started_at,finished_at,worker_id,heartbeat_at,target_count,settled_target_count,safe_error_code. States: queued,running,succeeded,completed_with_errors,interrupted. Unique requester/request_id and one partial-active index. Add `ops.matchmaking_run_users`: run_id,user_id,ordinal,state,started_at,finished_at,strategies_evaluated,strategies_skipped,unique_candidates_count,created_matches_count,existing_matches_skipped_count,safe_reason. Unique(run_id,user_id); ordinal derived from sorted captured IDs. Target IDs persist independently of later identity deletion so history can report missing users.

Target states: pending,running,succeeded,disabled_user,user_not_found,failed,commit_outcome_unknown,not_executed. Success counts are nonnegative and known; failure/uncertain/not-executed counts are NULL, never zero guesses. Persist bounded per-strategy skipped results in `ops.matchmaking_run_skipped_strategies(run_id,user_id,strategy_id,reason)` keyed by those IDs; no criteria copied. Fetch reasons separately in pages instead of embedding an unbounded array in run detail. No need to store the created Match entities or add a run FK to existing Matches: counts are operational results; the separate Matches tab reads durable Match rows.

Before each service call, durably transition the exact pending target to running under worker ownership. After its return, atomically persist the result/skipped reasons and increment settled_target_count once. Preserve existing safe failure codes; a service-reported unknown commit is a settled uncertain outcome and is not retried. Continue remaining users after individual service errors when guard/tracking remain healthy. Successful user with incomplete/unsupported strategy is acknowledged success with visible warnings, not a run execution failure. Run succeeds if every target is succeeded/disabled/missing; any failure/unknown => completed_with_errors. Distinguish skipped targets from successfully evaluated users in totals.

There is necessarily a gap between matcher commit and result-journal commit because matcher owns its transaction. If the process/tracking fails in that gap, preserve running/uncertain state, stop starting targets, and reconcile only after proving executor stopped. Do not infer counts by comparing table totals or replay a user automatically. Previously acknowledged results survive. A new explicit run is duplicate-safe but cannot reconstruct the first run's unknown result. This MVP accepts visible uncertainty rather than expanding the matcher transaction API.

Progress is settled_target_count/target_count labelled "users processed", with failed/skipped/unknown counts alongside it. Current user is indeterminate during its evaluation; no company-scan estimate.100% processed does not imply success. Aggregate match counts sum acknowledged results only and carry `counts_complete=false` if any attempted outcome is unknown/failed or any target not executed. A stale heartbeat is a freshness flag, not a terminal-state transition.

### 4. Shared execution admission and recovery

Reuse the pipeline guard and long-lived `shared-execution` advisory key and supervised process-group lifecycle. That session execution key is never acquired by HTTP trigger admission. This change's additive migration extends `ops.pipeline_execution_guard` with `resource_kind` (pipeline or matchmaking), optional `matchmaking_run_id`, and constraints permitting exactly the corresponding managed reference or no managed reference for standalone CLI. Existing rows map to pipeline; existing active owner/execution identity is preserved. Pipeline admission explicitly writes pipeline kind and remains independent of matcher imports. Only a neutral trusted execution-guard port/adapter is shared; no arbitrary executable or generic public job type is introduced.

The matching worker claims committed queued work, obtains the same dedicated session advisory lock, atomically claims the durable guard, records supervised owner/child identity before evaluation, and uses the existing bounded heartbeat/termination/reap protocol (15s heartbeat,60s stale,5s termination grace). If collection owns the guard, leave matching queued; full pipeline execution likewise waits/refuses while matcher owns it. Queued rows in the two job-specific tables can coexist; execution is exclusive, and admission order is best-effort with no FIFO guarantee. HTTP triggers do not hold a lock during execution.

Extend supported `python -m huginn.matchmaking` CLI wiring to acquire the same durable guard/supervised child around its existing explicit batch. Preserve arguments, successful batch JSON, and existing per-user failure behavior. Add pre-execution guard errors using the existing top-level `{error:{code,message}}` shape with safe codes `execution_busy` or `execution_unavailable` and exit1; invalid arguments/configuration retain exit2. These new errors mean no user evaluation started. Managed control uses the infrastructure service adapter, not this guarded public CLI, preventing double-locking. Guard and matcher must refer to the same PostgreSQL database. Other standalone ingestion/enrichment commands remain outside the initial shared guard and the existing runbook prohibition on concurrent use applies.

Worker restart processes queued work only, never automatically reclaims a running run. Trusted control CLI `reconcile (--run-id ... | --execution-id ...) --executor-stopped` requires exactly one reference and reuses proven host/process-start identity and resource-lock checks. For a managed run, mark abandoned running targets commit_outcome_unknown, pending targets not_executed, and run interrupted, then clear only the matching owner's guard. For a standalone matcher CLI execution, verify its matching resource identity and clear the proven-stopped owner's guard without fabricating run/user results. Release/reconciliation must dispatch on resource_kind: the pipeline reconcile CLI must refuse matching-owned guards, and matching reconcile must refuse pipeline owners. No heartbeat-age-only clearance or automatic rerun. Unknown final journal commit is resolved by rereading run/user state, never by invoking the matcher again.

### 5. APIs and bounded browser views

All admin responses/errors use Cache-Control:no-store and Vary:Cookie; existing safe envelope/422 mapping applies. Separate strict GET query models reject unknown query fields; limits1..100, bounded nonnegative offsets. Reject arbitrary commands, data-source configuration, user-supplied role, or DSN. History, user-result, and skipped-reason lists reuse management PageResponse[T] (`items,limit,offset,has_more`), not a new page protocol. TargetUserPageResponse extends that shape with total_eligible_count; run detail is a single bounded projection without embedded pages.

| Endpoint | Response/ordering |
| --- | --- |
| `GET /api/v1/admin/matchmaking/users` | search<=200,offset,limit; active identities page + total_eligible_count from same read snapshot; username ASC,id ASC |
| `POST /api/v1/admin/matchmaking/runs` |202 receipt `{id,state,requested_at,cutoff,as_of,target_count}` + Location; same-key receipt,422 empty targets,409 active/identity conflicts |
| `GET /api/v1/admin/matchmaking/runs` | page, optional validated state; requested_at DESC,id DESC |
| `GET /api/v1/admin/matchmaking/runs/{id}` | metadata/window/progress/freshness/safe totals; no unbounded target/Match arrays |
| `GET /api/v1/admin/matchmaking/runs/{id}/users` | paginated states/counts by ordinal; optional validated target state |
| `GET /api/v1/admin/matchmaking/runs/{id}/users/{user_id}/skipped-strategies` | page by strategy_id ASC; known safe reason values;404 if target not in that run |

Frontend `/admin/matchmaking` has run history and a compact trigger form; `/admin/matchmaking/runs/:id` has scope/window, progress, per-user result table, and expandable paginated skipped reasons. Reuse shared PrimeVue progress/table/status/loading/error components and current-session role; no alternative shell. Search/paging reaches beyond100 users and keeps selected IDs outside current pages visible (selected name retained in local form, server revalidates target). No default all-user selection. Trigger resolves server receipt and navigates to detail; uncertainty retains exact request input/ID and offers Check history or explicit Retry same request. Never automatic mutation retry or a new ID after response loss.

Poll visible queued/running detail/users every3s, visible history with active rows every10s; bounded transient backoff<=30s, cancel on hide/navigation, no retries401/403/404/422. Abort scoped requests and clear admin cache on403; standard session teardown on401. One final fetch on terminal transition; reload/deep links restore by runID. Current company matches are not an admin impersonation view; results table reports counts/reasons only. Link users to their own Matches tab through normal user navigation, not administrator-as-user access.

### 6. Owner overview contract

The `user-matches-view` owner query can read the newest own run-user row joined to run metadata, ordered requested_at DESC,run.id DESC and filtered by authenticated user ID. Its optional result is `{state,requested_at,started_at,finished_at,cutoff,as_of,tracking_stale,strategies_evaluated,strategies_skipped,created_matches_count,existing_matches_skipped_count}` with nullable counts unless acknowledged success. Exclude runID,requester,other targets,run-wide totals,private criteria, and internal errors. Current has_active_strategies is a separate management query. No recorded managed run does not prove an unmanaged legacy CLI never executed. A completed evaluation predating an ICP/strategy edit is not proof the latest draft/configuration has been evaluated.

### 7. Exact production inventory

New paths below are relative to `src/huginn/matchmaking_control/`. Requests/responses/value projections are frozen dataclasses; boundary validation/row models remain separate. Each service exposes execute(Request)->Response. Empty package markers only, no re-export umbrellas.

| Path | Named type/export |
| --- | --- |
| `domain/entities/matchmaking_run.py` | MatchmakingRun |
| `domain/value_objects/run_state.py` | RunState |
| `domain/value_objects/target_state.py` | TargetState |
| `domain/value_objects/run_target.py` | RunTarget |
| `domain/value_objects/requester.py` | Requester |
| `domain/errors/run.py` | ActiveRunConflictError, RequestIdentityConflictError |
| `application/protocols/run_reader.py` | RunReader |
| `application/protocols/target_user_query.py` | TargetUserQuery |
| `application/protocols/matchmaking_executor.py` | MatchmakingExecutor |
| `application/read_models/target_user.py` | TargetUser |
| `application/read_models/run_summary.py` | RunSummary |
| `application/read_models/run_detail.py` | RunDetail |
| `application/read_models/user_result.py` | UserResult |
| `application/read_models/skipped_strategy_result.py` | SkippedStrategyResult |
| `application/requests/trigger_run_request.py` | TriggerRunRequest |
| `application/responses/trigger_run_response.py` | TriggerRunResponse |
| `application/services/trigger_run_service.py` | TriggerRunService |
| `application/requests/list_target_users_request.py` | ListTargetUsersRequest |
| `application/responses/list_target_users_response.py` | ListTargetUsersResponse |
| `application/services/list_target_users_service.py` | ListTargetUsersService |
| `application/requests/list_runs_request.py` | ListRunsRequest |
| `application/responses/list_runs_response.py` | ListRunsResponse |
| `application/services/list_runs_service.py` | ListRunsService |
| `application/requests/get_run_request.py` | GetRunRequest |
| `application/responses/get_run_response.py` | GetRunResponse |
| `application/services/get_run_service.py` | GetRunService |
| `application/requests/list_user_results_request.py` | ListUserResultsRequest |
| `application/responses/list_user_results_response.py` | ListUserResultsResponse |
| `application/services/list_user_results_service.py` | ListUserResultsService |
| `application/requests/list_skipped_strategies_request.py` | ListSkippedStrategiesRequest |
| `application/responses/list_skipped_strategies_response.py` | ListSkippedStrategiesResponse |
| `application/services/list_skipped_strategies_service.py` | ListSkippedStrategiesService |
| `application/requests/execute_run_request.py` | ExecuteRunRequest |
| `application/responses/execute_run_response.py` | ExecuteRunResponse |
| `application/services/execute_run_service.py` | ExecuteRunService |
| `application/requests/reconcile_run_request.py` | ReconcileRunRequest |
| `application/responses/reconcile_run_response.py` | ReconcileRunResponse |
| `application/services/reconcile_run_service.py` | ReconcileRunService |
| `application/requests/reconcile_execution_request.py` | ReconcileExecutionRequest; standalone matching execution ID/proven-stopped identity |
| `application/responses/reconcile_execution_response.py` | ReconcileExecutionResponse |
| `application/services/reconcile_execution_service.py` | ReconcileExecutionService |
| `application/errors/execution.py` | ResultTrackingUncertainError |
| `persistence/contracts/repositories/run.py` | RunRepository |
| `persistence/contracts/unit_of_work.py` | MatchmakingControlUnitOfWork |
| `persistence/repositories/run_repository.py` | PostgresRunRepository |
| `persistence/queries/run_reader.py` | PostgresRunReader |
| `persistence/queries/target_user_query.py` | PostgresTargetUserQuery |
| `persistence/row_models/matchmaking_run.py` | MatchmakingRunRow |
| `persistence/row_models/user_result.py` | UserResultRow |
| `persistence/row_models/target_user.py` | TargetUserRow |
| `persistence/row_models/skipped_strategy_result.py` | SkippedStrategyResultRow |
| `persistence/database/unit_of_work.py` | PostgresMatchmakingControlUnitOfWork |
| `infrastructure/service_matchmaking_executor.py` | ServiceMatchmakingExecutor |
| `presentation/api/requests/trigger_run.py` | TriggerRunBody |
| `presentation/api/requests/single_user_target.py` | SingleUserTargetBody |
| `presentation/api/requests/all_eligible_target.py` | AllEligibleTargetBody |
| `presentation/api/requests/list_target_users.py` | ListTargetUsersQuery |
| `presentation/api/requests/list_runs.py` | ListRunsQuery |
| `presentation/api/requests/list_user_results.py` | ListUserResultsQuery |
| `presentation/api/requests/list_skipped_strategies.py` | ListSkippedStrategiesQuery |
| `presentation/api/responses/run_receipt.py` | RunReceiptResponse |
| `presentation/api/responses/run_summary.py` | RunSummaryResponse |
| `presentation/api/responses/run_detail.py` | RunDetailResponse |
| `presentation/api/responses/user_result.py` | UserResultResponse |
| `presentation/api/responses/target_user.py` | TargetUserResponse |
| `presentation/api/responses/target_user_page.py` | TargetUserPageResponse; adds total_eligible_count to existing page shape |
| `presentation/api/responses/skipped_strategy_result.py` | SkippedStrategyResultResponse |
| `presentation/api/routers/runs.py` | router |
| `presentation/cli/worker.py` | main |
| `presentation/cli/executor.py` | main; trusted supervised child |
| `presentation/cli/reconcile.py` | main |
| `bootstrap.py` | create_matchmaking_control_services |
| `config.py` | MatchmakingControlConfig |
| `__main__.py` | main; worker/reconcile/executor dispatcher |

Existing narrow extensions: matcher bootstrap build_service; matcher CLI trusted guarded batch wiring; pipeline shared execution_guard/supervisor adapters expose the fixed resource dispatch and refuse mismatched reconciliation; management app/dependency composition mounts this router. Migration `db/schema/ops-matchmaking-control.sql` creates result tables/indices/throttle namespace and extends guard without resetting existing state. Keep base `db/schema/ops.sql` before Bronze/Gold as it is; apply this migration after Gold, operational tables and `ops-pipeline-control.sql` in both fresh and existing installations so new foreign keys have valid dependencies. Update existing bootstrap fixture schema loaders and `docs/management-foundation.md`, `docs/matchmaking.md`, schema README/runbooks to reflect that order and guarded CLI error/recovery contracts. No new driver wrapper. Generated foundation schema/types change together.

Frontend paths relative to `frontend/src/features/matchmaking/`:

| Path | Named type/export |
| --- | --- |
| `pages/MatchmakingHistoryPage.vue` | MatchmakingHistoryPage |
| `pages/MatchmakingRunPage.vue` | MatchmakingRunPage |
| `components/MatchmakingTriggerForm.vue` | MatchmakingTriggerForm |
| `components/TargetUserSelect.vue` | TargetUserSelect |
| `components/SignalWindowFields.vue` | SignalWindowFields |
| `components/MatchmakingProgress.vue` | MatchmakingProgress |
| `components/UserResultTable.vue` | UserResultTable |
| `components/SkippedStrategyList.vue` | SkippedStrategyList |
| `api/listTargetUsers.ts` | listTargetUsers |
| `api/triggerMatchmakingRun.ts` | triggerMatchmakingRun |
| `api/listMatchmakingRuns.ts` | listMatchmakingRuns |
| `api/getMatchmakingRun.ts` | getMatchmakingRun |
| `api/listUserResults.ts` | listUserResults |
| `api/listSkippedStrategies.ts` | listSkippedStrategies |
| `composables/useMatchmakingHistory.ts` | useMatchmakingHistory |
| `composables/useMatchmakingRun.ts` | useMatchmakingRun |
| `composables/useTargetUsers.ts` | useTargetUsers |
| `composables/useMatchmakingTrigger.ts` | useMatchmakingTrigger |
| `forms/matchmakingTriggerDraft.ts` | MatchmakingTriggerDraft |
| `forms/serializeMatchmakingTrigger.ts` | serializeMatchmakingTrigger |
| `navigation/validateMatchmakingQuery.ts` | validateMatchmakingQuery |
| `routes.ts` | matchmakingRoutes |

### 8. Verification scope

Prefer a few meaningful integrated scenarios: authorized single/all-user queue through existing matcher; target snapshot beyond100; duplicate receipt/conflict and concurrent worker/CLI/collection admission; partial failures/unknown commits/tracking crash; own-only Matches overview; browser progress/window/pagination/role demotion. Use deterministic harmless pipeline fixtures and disposable PostgreSQL16, preserving shared real data. Existing evaluator suite already tests matching rules; do not duplicate every criterion case. Required frontend schema/type/lint/format/unit/build/browser, Python3.14 compile/Ruff/full live-PG pytest, strict OpenSpec, exact inventory, and fresh Sol high review remain completion gates. Reuse installed tools; ask before any download. Future push checks use standalone clean checkout, never linked-worktree hooks.

## Risks / Trade-offs

- Result commit gap -> explicit uncertainty, durable ownership, no replay; counts are acknowledged results only.
- Long single-user evaluation -> indeterminate user activity plus heartbeat, not a fabricated inner progress percentage.
- Collection/matching contention -> shared durable guard and visible waiting; MVP serial execution, no FIFO scheduling promise.
- Current configuration differs from trigger-time configuration -> fixed users/window, explicit current-at-evaluation semantics, no historical reasoning claims.
- Guard extension affects existing CLI/runtime -> additive migration with active-owner preservation, compatible explicit resource dispatch, disposable race/recovery verification before rollout.

## Migration Plan

Apply after pipeline roles/guard are deployed from the actual merged source base, preserving primary edits and previews. Fresh setup retains base ops -> Bronze -> Silver -> Gold -> operational order, then role/pipeline-control migrations, then `ops-matchmaking-control.sql`; match identity/signal-index migrations remain existing matcher prerequisites. Existing installations apply only compatible additive migrations after checking their dependencies. Verify both setup paths on disposable PostgreSQL16; no boot DDL. Review backups and apply to real data only when later authorized. Deploy backward-compatible guard adapters for collection and matching together before enabling admin trigger, stop old unguarded matcher CLI jobs, and start the dedicated matching worker separately from lifecycle mail. Existing managed pipeline history and Match records are preserved. Rollback disables new trigger/worker only after exact executor stop; retain result tables/guard ownership and never remove constraints during execution. Document explicit admin assignment, CLI/worker operation, no-concurrent standalone ingestion/enrichment rule, stale/reconciliation behavior, and local logs.
