# Matchmaking operator

`huginn.matchmaking` creates missing `operational.match` rows for an explicit
set of Users. It reads active discovery strategies and ICPs from operational
tables and eligible companies/signals from Gold. Each User runs in its own
transaction, and the batch continues after a User failure.

This slice only creates Matches. It does not score or rank candidates, record
evidence, send a digest, update an existing Match, or resurface dismissed or
previously created Matches. Existing workflow status and notes are preserved.
The response order is deterministic by User and Company UUID.

## Database setup

The runtime connects to the PostgreSQL database containing both the
`operational` and `gold` schemas. For a fresh database, apply the regular
bootstrap files in dependency order, with Gold before operational because
operational tables reference Gold. For an existing database, keep the current
schemas and apply only these additive migrations before running the operator:

1. `db/schema/operational-match-user-company-unique.sql` installs or validates
   the unique `operational.match_user_company_unique` constraint. It stops if
   duplicate User–Company pairs need explicit reconciliation.
2. `db/schema/gold-company-signal-matchmaking-index.sql` installs or validates
   the `gold.company_signal_company_occurred_at_idx` lookup index.

Fresh installs include the same constraint and index in `operational.sql` and
`gold.sql`. Migrations are idempotent for compatible existing objects. Run
them with a schema-administration credential; the runtime credential should
have `USAGE` on `operational` and `gold`, `SELECT` on the configuration and
Gold columns read by matchmaking, and `SELECT` on the Match columns used by
`RETURNING` and the `(user_id, company_id)` conflict target. It also needs
`INSERT` on `operational.match` columns `user_id`, `company_id`, `status`, and
`notes`. The unique constraint must be present for the `ON CONFLICT` arbiter.
The CLI does not create schemas, run migrations, or change grants.

## Run a batch

Set `HUGINN_MATCHMAKING_DATABASE_URL` to a psycopg PostgreSQL connection string
for that database. The DSN is read from the environment and is never accepted
as a command-line argument.

```sh
export HUGINN_MATCHMAKING_DATABASE_URL='postgresql://matchmaking:secret@localhost/huginn'
rtk proxy python -m huginn.matchmaking \
  --user-id 11111111-1111-4111-8111-111111111111 \
  --user-id 22222222-2222-4222-8222-222222222222 \
  --cutoff 2026-09-01T00:00:00Z \
  --as-of 2026-10-01T00:00:00+00:00
```

Repeat `--user-id` for additional Users. At least one ID and `--cutoff` are
required. Timestamps must be ISO-8601 values with `Z` or an explicit UTC
offset. `--as-of` is optional and, when omitted, one current time is captured
for the complete batch. The signal window includes both cutoff and as-of.
Invalid IDs or timestamps are rejected before configuration or database
readiness checks.

### Matching behavior

`cutoff` and `as-of` bound an inclusive signal window. `as-of` defaults to one
time captured for the full batch, and every User receives the same UTC window.
Candidate qualification requires at least one signal inside that window. A
company must also match at least one industry, one selected company-size band,
and one country in an active ICP. Any current signal type can satisfy the
window. Values within each dimension are ORed;
industries, size, and country are combined with AND. A User qualifies once if
any active strategy qualifies the company.

Industry and country comparisons lowercase text and trim ASCII spaces at both
ends (`lower(btrim(...))`). The comparison does not infer aliases, synonyms,
substrings, regional membership, or semantic matches. For example, `USA` does
not match `United States`. The sector value `Unspecified` is treated as missing
classification and cannot satisfy an industry criterion; using it as a
positive criterion makes that ICP invalid. Null or blank company sector,
size, or country data cannot satisfy a required positive dimension.

Company ID, industry, and country exclusions veto a company across all
positive combinations within their ICP. An industry exclusion checks every
company sector, even when another sector matched positively. Exclusions belong
to one ICP: a company rejected by one strategy can still qualify through a
separate strategy, and contributes only once to the User's result. Regions
are recognized in ICP data but unsupported. A well-formed positive or
excluded region skips that strategy as `unsupported_region`; the service does
not infer region membership. Invalid stored shapes or items skip as
`invalid_icp`; any empty positive dimension skips as `incomplete_icp`. Invalid
criteria take precedence over an empty positive dimension, which takes
precedence over unsupported regions. Skipped strategies report one of those
three reason codes without exposing their criteria.

### Per-User transaction and retry behavior

The service reads the User's account, active strategies, ICPs, and candidate
companies in one PostgreSQL `REPEATABLE READ` transaction, then inserts sorted
distinct Company IDs. The batch is serial and each User has an independent
transaction. Configuration or Gold changes after a User's snapshot take
effect on a later run. A failure before acknowledged commit rolls back that
User's attempt; tentative Matches, counts, and skipped-strategy results are
discarded, while other Users in the batch continue.

Only serialization failures (`40001`) and deadlocks (`40P01`) retry. The
service makes at most three attempts, waiting 0.05 seconds and then 0.10
seconds between retries. Each retry repeats the full User transaction with
the original signal window. Other database errors fail that User without
retrying.

If the connection is lost or times out while `COMMIT` is in flight and the
server outcome is unacknowledged, the result is `commit_outcome_unknown`. The
service does not retry or claim that no Match was created. An explicit rerun
is duplicate-safe because the database enforces one Match per User and
Company, but it cannot establish whether the earlier invocation committed.
Rolling back the service version does not require removing the uniqueness
constraint or deleting Matches; keep the durable identity constraint in
place.

### Python API

The single-User API is
`MatchmakingService.execute(MatchmakingRequest) -> MatchmakingResponse`. The
batch API is
`MatchmakingBatchService.execute(BatchMatchmakingRequest) -> BatchMatchmakingResponse`.
Requests carry `user_id` (or explicit `user_ids`), a required timezone-aware
`cutoff`, and optional timezone-aware `as_of`. The batch service deduplicates
and sorts IDs and accepts an empty tuple without database access; the CLI
requires at least one User ID.

The CLI writes one JSON object to standard output. A successful batch has
exactly `cutoff`, `as_of`, `responses`, and `failures` at the top level, even
when one User was requested. Each response has exactly `user_id`, `status`,
`cutoff`, `as_of`, `strategies_evaluated`, `strategies_skipped`,
`unique_candidates_count`, `created_matches`,
`existing_matches_skipped_count`, and `skipped_strategies`. A created Match
contains `id`, `user_id`, `company_id`, `status`, `notes`, `created_at`, and
`updated_at`. A skipped strategy contains `strategy_id` and `reason`; a User
failure contains `user_id` and `reason`. UUIDs are strings, timestamps are
UTC ISO-8601 values, and enum values are strings. Statuses are `succeeded`,
`disabled_user`, and `user_not_found`; failure reasons are
`database_unavailable`, `database_failure`, `retries_exhausted`, and
`commit_outcome_unknown`.

Configuration and argument errors use `{ "error": { "code": "...", "message": "..." } }`.
Error messages do not include database details or exception text.

Exit codes:

| Code | Meaning |
|---|---|
| `0` | The batch completed without database failures, including disabled or missing Users and skipped strategies. |
| `1` | One or more Users failed, or shared execution was busy/unavailable before evaluation started. |
| `2` | Arguments or runtime database configuration are invalid. |

The Python batch service also supports an empty tuple of User IDs without
database access. The CLI requires at least one ID so an operator invocation
always names its intended scope.

## Future work

The module is not scheduled by ELT and does not deliver user-facing output.
Scheduler integration, scoring, evidence snapshots, digest composition,
delivery, and resurfacing need later design and implementation.

## Administrator execution and shared guard

1. Apply the existing matcher identity/signal-index migrations, then the role and pipeline-control migrations, then `db/schema/ops-matchmaking-control.sql`. The base bootstrap keeps `ops.sql` before Bronze and Gold; control migrations run after Gold and operational tables. Apply additive upgrades with a schema administrator, never from application startup.
2. Assign an administrator explicitly through the account-admin command documented in [management-foundation.md](management-foundation.md). Existing accounts remain ordinary users. Roles are checked against the current account for every request.
3. Configure the management API, collection worker, matching worker, and matcher CLI to use the same PostgreSQL database. The matching worker and standalone matcher both read `HUGINN_MATCHMAKING_DATABASE_URL`. A dedicated session lock and durable guard in that database cover managed matching, the full pipeline CLI, and standalone matcher CLI.
4. Stop old unguarded matcher jobs before enabling the new worker. Deploy both guard-aware adapters together. Standalone ingestion-only and enrichment entrypoints remain outside this guard; never run them concurrently with managed collection or matching.

Start the dedicated serial matching worker separately from lifecycle mail:

```sh
rtk proxy python -m huginn.matchmaking_control worker
rtk proxy python -m huginn.matchmaking_control worker --once
```

Administrator requests queue an immutable sorted target snapshot and UTC signal window. The receipt target count is authoritative; current configuration is read when each target is evaluated. The default browser window is visibly editable at 30 days. There is no automatic matching after collection and no automatic replay after a worker restart. Queued collection and matching histories can coexist while execution remains exclusive. A busy guard leaves a matching receipt queued.

The standalone matcher keeps its arguments, successful batch JSON, and per-user failure behavior. New pre-execution failures use the same top-level error envelope with safe codes `execution_busy` or `execution_unavailable` and exit 1. These errors mean no target evaluation began. Invalid arguments/configuration retain exit 2. Runtime credentials additionally need reads/writes for the shared ops guard; managed matching needs ops run/result/throttle tables.

### Unknown results and stopped-executor recovery

A heartbeat older than 60 seconds is stale tracking, not proof that work stopped. Supervision heartbeats every 15 seconds and terminates/reaps the child process group with a 5-second grace when tracking is lost. A matcher commit followed by an unacknowledged journal commit can leave the current target unknown. Previously acknowledged counts remain visible; failed, unknown, and not-executed target counts remain null. Counts are not inferred from Match table totals.

Inspect the exact durable owner, host, supervisor/child PID, and process-start identity before recovery. Stop that supervisor and child process group, verify the process-start identities no longer exist, then run exactly one form:

```sh
rtk proxy python -m huginn.matchmaking_control reconcile --run-id RUN_UUID --executor-stopped
rtk proxy python -m huginn.matchmaking_control reconcile --execution-id EXECUTION_UUID --executor-stopped
```

The command independently verifies stopped host/process identities and the resource lock. It refuses live executors and pipeline-owned guards. Pipeline reconciliation likewise refuses matching-owned guards. Managed reconciliation retains acknowledged results, marks an abandoned running target `commit_outcome_unknown`, pending targets `not_executed`, and the run `interrupted`, then clears only that exact matching owner. Standalone reconciliation clears its proven-stopped matching guard without inventing managed results. Never clear ownership based only on heartbeat age.

An explicit new run remains creation-only and duplicate-safe, but cannot reconstruct an earlier uncertain result. On a lost HTTP receipt, retry only the same request ID and exact input, or check history; do not automatically submit a fresh identity.

Rollback disables trigger access and the matching worker after proving the exact executor stopped. Retain result tables, guard ownership, and Match uniqueness; do not remove constraints, delete history, or clear active ownership during rollback.
