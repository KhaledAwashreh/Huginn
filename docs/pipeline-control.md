# Pipeline operations

Administrator triggers enqueue the existing full HN, YC and EU-Startups pipeline.
A dedicated synchronous worker runs committed work independently of HTTP.
[ADR-0017](../adr/0017-durable-pipeline-execution-control.md) records admission and recovery.

## Deployment and account assignment

1. Verify the selected database has all seven base files documented in
   [schema bootstrap](../db/schema/README.md). Apply these additive migrations
   only after `gold.sql` and `operational.sql`:

   ```bash
   rtk proxy psql "$HUGINN_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/operational-account-role.sql
   rtk proxy psql "$HUGINN_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/ops-pipeline-control.sql
   ```

2. Configure `HUGINN_MANAGEMENT_DATABASE_URL` and `HUGINN_DATABASE_URL` for the
   same production database. The management application keeps its explicit
   management DSN; the worker and existing ELT read the ELT DSN. Set the existing
   required YC API configuration for the child executor. No DSN is accepted in
   the trigger body, and application construction applies no migrations.

3. Assign an existing account explicitly through trusted operator tooling:

   ```bash
   rtk proxy env PYTHONPATH=src .venv/bin/python -m huginn.management.admin account assign-role --username operator --role admin --confirm
   ```

   Existing accounts, public signup and trusted provisioning default to `user`.
   Demote with the same command and `--role user --confirm`; the next authenticated
   request sees the current database role, including a still-active session.
   Assignment changes role only and preserves disabled state. There is no HTTP
   role editor.

4. Stop the old full-pipeline cron command before starting the worker. Replace
   direct full-pipeline cron use with the supported guarded full command or a
   deliberate administrator trigger. Run the worker under a process supervisor:

   ```bash
   rtk proxy env PYTHONPATH=src .venv/bin/python -m huginn.pipeline_control worker
   rtk proxy env PYTHONPATH=src .venv/bin/python -m huginn.pipeline_control worker --once
   ```

   `--once` checks one queued invocation and exits; a busy resource leaves it
   queued. Polling waits two seconds between checks. SIGINT/SIGTERM stop polling
   and terminate a running owned child before settlement. The supported
   `python -m huginn.elt` uses the same guard and exits nonzero when busy.
   Standalone ingestion and EU enrichment commands remain outside this guard;
   operators must not run them concurrently with full pipeline execution.

## Private HTTP contracts

1. `POST /api/v1/admin/pipeline/invocations` accepts only `{request_id: UUID}`,
   requires the administrator session and its `X-CSRF-Token`, and returns a
   committed queued receipt with HTTP 202 and detail `Location`. Retry the same
   account/request ID after a lost response. A distinct active invocation causes
   safe HTTP 409; ten distinct trigger requests per administrator per hour is
   the default admission bound. Harmless same-key lookups do not consume it.
2. History uses limit 1 through 100, nonnegative offset and an optional supported
   state filter, ordered newest request timestamp and ID first. Detail returns
   the immutable nine-stage plan and explicitly linked stage/source executions.
   Events use a nonnegative `after_sequence` cursor and limit 1 through 100,
   ordered by invocation-local sequence. Poll detail/events at a bounded interval
   and stop after a terminal outcome; no streaming transport is required.
3. Company results use limit 1 through 100 and nonnegative offset, ordered by
   company UUID. The response includes attribution tracking state, total count,
   paging bounds and current allowed Gold fields. Membership means processed or
   written by this invocation, not newly discovered or changed. Contact fields
   and notes are excluded. Current fields can change after the run; membership
   remains durable. Unknown legacy membership is an empty `unknown_legacy` page.
4. Every route checks authoritative active administrator status and returns
   `Cache-Control: no-store`. Events and safe errors never contain raw payloads,
   credentials, DSNs, database exception text, sessions or recovery proofs.
   Aggregate `ingestion` measures failed sources; it never reports that number
   as rows or a completion percentage. Stage failed/skipped outcomes remain
   distinct; interruption does not fabricate skipped jobs or successful progress.

## Recovery

1. A stale heartbeat (over 60 seconds) indicates uncertain tracking. It does not
   release the guard, mark success, or allow replay. Worker restart claims queued
   work only; running work remains blocked. Heartbeats normally occur every
   15 seconds and each database statement is bounded to two seconds.
2. Inspect the exact persisted owner host, supervisor PID/start identity and
   executor PID/start identity in `ops.pipeline_execution_guard`. Inspect the
   actual host/process group. The executor creates its own process group and
   waits for the persisted start handshake before running any stage. If the
   supervisor dies, stop the entire old executor group first. Do not treat an
   available advisory lock or old heartbeat as stopped-process evidence.
3. The supervisor sends TERM, waits up to five seconds, escalates to KILL and
   reaps its child. The durable gate stays active until local group members are
   gone and owner-conditional finalization is committed. If cleanup or tracking
   cannot be proven, retain the blocker for trusted recovery. A previously sent
   remote request can finish remotely; no second local executor is admitted.
4. On the owning host, after the exact supervisor and executor group are stopped,
   use one of the explicit recovery identities:

   ```bash
   rtk proxy env PYTHONPATH=src .venv/bin/python -m huginn.pipeline_control reconcile --invocation-id INVOCATION_UUID --executor-stopped
   rtk proxy env PYTHONPATH=src .venv/bin/python -m huginn.pipeline_control reconcile --execution-id EXECUTION_UUID --executor-stopped
   ```

   The command verifies host/process-start identity, refuses a live supervisor
   or executor group, obtains the shared resource lock, and atomically records
   interruption and clears matching ownership. Standalone CLI recovery never
   fabricates an invocation. Reconciliation preserves completed stages and
   earlier stage commits. Run an explicit new invocation for a full retry.
   Do not reset invocation state, remove job rows, or infer company results.

## Shared resource and rollback

The short transaction advisory resource `(1213548366, 1)` is pipeline trigger
admission; the long-lived session resource `(1213548366, 2)` is shared execution.
A trigger never acquires the execution resource. Both full CLI and worker require
that lock and the durable singleton guard before starting a child. Storage
unavailability denies execution. The guard is not a lease and never expires.

`admin-matchmaking-execution` owns the future additive `resource_kind` and
matching-run reference migration. Its executor must use the same execution
lock and guard, with a distinct matcher operation. An already active guard
blocks pipeline callers regardless of that future owner kind. The pipeline
imports and records no matcher work.

Rollback stops managed workers and blocks new trigger routes, then proves all
old executor groups stopped before reverting application code. Keep the
additive role/control tables, job lineage and company attribution for audit;
remove neither data nor columns. Retain guarded full CLI scheduling during
cutover. An older unguarded CLI must not run while any managed or shared-resource
executor can still be active. Base `ops.sql` remains unchanged, and legacy
unlinked jobs retain their original states and nullable lineage.

The matching-control upgrade extends the same execution guard with a fixed resource kind. Apply `ops-matchmaking-control.sql` after this setup before running updated worker/CLI binaries. Collection always claims `pipeline`; matching always claims `matchmaking`. Queued work can coexist, while matching worker and supported matcher CLI hold the same execution lock as collection. Pipeline recovery refuses matching ownership; use the matching recovery commands in [matchmaking.md](matchmaking.md). Deploy the updated guard adapters together and stop old unguarded matcher processes.
