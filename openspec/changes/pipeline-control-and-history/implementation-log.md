# Pipeline control implementation log

Started 2026-10-09. Approved apply workflow; implementation remains local without commit/push/PR/Jira. Primary checkout, configuration runtime, other worktrees and real PostgreSQL data are preserved.

## Baseline and authorization

- Fetched origin/master successfully; actual merged base is `7fc076a646af23d7502f9754f62dfdcb97ed04c4` (PR23 foundation/lifecycle). Dedicated worktree `.worktrees/pipeline-control-and-history`, branch `feature/pipeline-control-and-history`, created from this exact commit without advancing primary master.
- Selected untracked planning change inspected and all five files copied byte-for-byte from the primary checkout. Other planning changes are not copied or modified. Existing configuration implementation remains uncommitted in its separate running worktree; backend pipeline work is independent of those UI/metadata additions.
- Primary ops writer SHA256 captured privately in `/tmp/huginn-pipeline-baseline.json` for preservation checks; its user-owned edit was not copied. Existing worktree listing/status recorded before creation. Interview/presentation files and unrelated changes remain untouched.
- Installed foundation Python3.14/tooling and frontend dependencies reused via ignored `.venv`/`frontend/node_modules` symlinks. Installed Node24 is available in the configuration worktree's private runtime directory. No dependency/browser downloads or installation authorized.
- No real-data migration, source collection, matcher execution, user role assignment, or preview restart performed. Database verification will use disposable PostgreSQL16 only.

## Existing graph and metrics verified

Inspected merged `elt/__main__.py`, `elt/stage_runner.py`, `elt/materialization.py`, and clean merged `ops/postgres_job_run_writer.py` before implementation. Nine stages: ingestion; ingestion.eu_startups; silver.hn_staging; silver.yc_staging; silver.eu_startups_staging; silver.signal_resolution; silver.manual_review; gold.company; gold.company_signal. The three staging dependencies join at shared resolution. Gold depends on resolution and company-signal also on company; manual-review queue failure does not block Gold. Source children remain hn/yc/eu_startups. Aggregate ingestion returns failed-source count, not rows written. Legacy stage tracking is best-effort. CompanyWriter uses one repository transaction across its entire Gold company batch.

## Implementation checkpoint

Task1.1 complete. Remaining roles, durable API/persistence, lineage, supervised worker/CLI/recovery, and verification proceed in dependency order. Explicit Sol medium integrates narrow Luna groups; final fresh-context Sol high review and parent reruns are required. Tests will establish meaningful authorization/queue/ownership/transaction/process scenarios rather than mirror every field.


## Integrated API and verification checkpoint

- Protected POST admission plus GET history/detail/events/companies are mounted in the existing management server. Authoritative session roles and CSRF guard admission; strict unknown fields and bounded query values, safe error envelopes, Location receipts, private response headers and company field allowlists are verified. No pipeline execution runs inside an HTTP request.
- Independent parent reruns passed focused API/application/OpenAPI checks (19), additive fresh/legacy migration and query scenarios (3), frontend offline schema/type/lint/format/unit/build (92 units), and existing browser gates (9). Browsers used disposable PostgreSQL, installed Chromium, and API8010/UI4183/mail8035, preserving the existing preview. Existing browser fixture port/executable overrides were reused from the configuration worktree without copying feature code.
- First full Python suite completed 1455 passed / 6 failed. Independent integration inspection found invalid SET-result fetching, owner-ID mismatch during queue transition, and claim-row/FK lock incompatibility. These fixes are now present; focused worker verification and full suite rerun remain pending. Initial failures included cascading active invocation contamination and a process cleanup timeout; no failure is waived.
- Exact production inventory initially found 101 planned files / 103 implemented. Added explicit planning rows for InvocationNotFoundError and TriggerRateLimitError, which implement already-required 404/429 outcomes. This corrects the omitted error inventory without changing product scope.
- Fresh Sol high review is in progress. Current implementation remains local, with no real-data changes, commits, pushes, PRs or Jira writes.

## Worker, lineage and recovery verification checkpoint

1. Local implementation adds explicit invocation and parent-stage context to the
   existing ELT runner and nested HN/YC/EU writers. Gold materialization forwards
   its exact stage context; company upserts return persisted UUIDs and attribution
   uses the existing batch cursor. Legacy tracking remains nullable/best effort.
2. Frozen application/domain/contracts and strict persistence row validation are
   separated by the approved inventory. Guard repository contracts return domain
   ownership plus scalar executor data, never persistence row models. Existing
   management database/session adapters are reused with optional bounded control
   statement timeouts; every control factory uses 2000ms.
3. Failing-first grouped managed tracking and SQL return tests established start
   gating, stable lineage and terminal tracking uncertainty. A focused existing
   ELT/source/Gold suite passed 88 tests. The final grouped live PostgreSQL16
   execution/query/trigger/tracking/Gold selection passed 47 tests in 8.61 seconds.
   All database cases used the stamped disposable harness; no scraper ran.
4. Actual RunQueuedInvocationService tests supervise harmless real children that
   verify running invocation and persisted child identity before receiving GO.
   Succeeded/failed/tracking-interrupted outcomes settle atomically. A supported
   full CLI exits busy while standalone ownership is active; queued managed work
   stays unstarted, then executes after release. Claims use FOR NO KEY UPDATE
   SKIP LOCKED so independent guard FK key-share locking remains compatible.
5. Real process tests cover mid-fetch guard connection loss, process-group TERM /
   KILL cleanup and reaping, and SIGKILL of an actual supervisor with an orphaned
   executor. The durable gate blocks admission after advisory release; live
   process recovery is refused. Exact stopped host / boot-ID / PID-start identity
   permits trusted reconciliation, retaining completed stages. A guard stranded
   before the running commit can safely reconcile its queued unstarted invocation.
6. Gold live tests verify both persisted UUID return shapes, whole-batch rollback
   of companies and attribution, retry uniqueness, deterministic bounded result
   paging and privacy. Source/stage successes and failed aggregate dependencies
   remain the ADR0014 graph; unknown failed/running/skipped counters stay unknown.
7. Python3.14 compilation, Ruff check and Ruff format checks pass on the current
   complete workspace (722 formatted files). Operator CLI help and role assignment
   arguments were checked without touching configured databases. The runbook and
   ADR0017 document migration/cutover, polling, recovery and rollback plus the
   future distinct matching-resource additive guard boundary.
8. Fresh Sol high review and parent independent full-suite/frontend/browser/schema
   gates remain the final task4.5 checkpoint. No commits, pushes, PR/Jira writes,
   shared migrations, user-data changes or preview restarts were performed.


## Final parent verification and handoff

Completed 2026-10-09: all22 tasks checked for pipeline-control-and-history. Parent inspected delegated production diffs and independently verified the exact completed worktree.

- Final full pytest: **1473 passed**, including live disposable PostgreSQL16 integrations (235.84s). Earlier full rerun1469 passed; the final rerun includes all later test-only variants. Focused parent reruns also passed actual administrator session promotion/demotion and durable receipts (9 combined adapter/API tests), all control tests (43 at that checkpoint), and final reconciliation/manual-review variants (3). No real sources were fetched.
- Python3.14 compileall passed for src/tests/scripts. Whole-workspace Ruff check and format passed,722 formatted Python files. git diff --check passed.
- Foundation frontend gates passed after final API generation: offline api:check, typecheck, lint, format,92 unit tests and production build. Existing browser gates:9 passed on disposable PostgreSQL, isolated API8010/UI4183/mail8035 and installed Chromium; no downloads.
- Strict OpenSpec validation passed. Exact production inventory/domain imports passed:103 control files, every path and named class matches design. The two previously omitted404/429 error inventory entries and optional shared-client timeout setting are documented as routine corrections.
- Fresh-context explicit Sol high review is clear with no unresolved actionable P1/P2 findings; see review.md. Parent verified every resolution and independently reran the live checks.
- Original primary ops edit remains byte-for-byte unchanged; original untracked planning tasks, unrelated changes and existing worktrees remain preserved. Read-only health checks confirmed the existing API8000 and UI4173 preview are healthy. No live schema migration, role assignment, collection/matching run, shared data reset, preview restart, commit, push, PR or Jira update occurred.

This completed slice is the backend dependency. Admin collection screens, separate matchmaking execution/UI, and user Matches workspace remain subsequent approved plans. The new backend is local in this dedicated feature worktree and is not deployed into the real-data preview. Future push verification must use a standalone clean checkout.
