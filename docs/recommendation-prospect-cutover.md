# Recommendation and prospect cutover

Use this procedure for a specifically authorized deployment target. The implementation
does not deploy, schedule mail, clean a persistent database, or reconcile sources
automatically. Rehearse against an owned disposable copy before changing that target.

Business owns configuration, recommendations, suppression and prospects. User remains
the acting person; Account remains authentication. Shared Gold Companies and retained
Bronze/Silver/Gold data are preserved. Legacy Match and batch rows are obsolete derived
workflow data and are not converted into prospects.

## Inspect and quiesce the target

1. Identify the exact database, deployed revision, web processes, weekly cron/systemd
   jobs and old matching workers. The management and ELT DSNs must address the same
   intended PostgreSQL database. Do not infer a host scheduler from repository files.
2. Stop old web writers and the old `matching-worker` using the deployed configuration
   before replacing it. Pause weekly jobs and drain collection work. The new Compose
   file has no matching worker. Stopping a process does not settle an uncertain email
   or prove that an executor has stopped.
3. Inspect `ops.pipeline_execution_guard`, `ops.matchmaking_runs` and
   `ops.matchmaking_run_users`. Preserve their audit rows. Reconcile an orphaned
   execution only through the existing exact-identity recovery command after proving
   it stopped. Live and counterpart-owned executors remain protected:

   ```sh
   rtk proxy uv run python -m huginn.matchmaking_control reconcile --help
   rtk proxy uv run python -m huginn.pipeline_control reconcile --help
   ```

   Do not mark a live run finished or clear guard rows directly to make cleanup pass.
   A queued legacy run is a failed preflight: the retired worker will not execute it.
   Resolve that target state explicitly before repeating this procedure.
4. Back up the target to private storage. Record exact table counts and retained IDs,
   profile/configuration values, consent, source lineage and pipeline audits before
   setup. Inspect the obsolete tables listed below and any existing new workflow
   tables. Resolve legacy Sending/Unknown attempts explicitly before cleanup; they
   cannot be assumed unsent because time passed.
5. Set `HUGINN_DISCOVERY_NEW_WORK_ENABLED=false` for the new web and scheduled command
   environment. This flag is read when the process loads its configuration. Old
   deployed code may not implement it, so it does not replace stopping old writers.

The cleanup target list, in deletion order, is:

| Group | Tables in `operational` |
| --- | --- |
| Legacy communication | `communication_turn`, `communication_revision`, `communication_version`, `communication` |
| Legacy relationship context | `activity`, `match_feedback`, `match_score`, `match_source_evidence`, `match` |
| Legacy delivery and batches | `weekly_digest_deliveries`, `recommendation_feedback`, `recommendation_batches` |

Accounts, Users, Business fields, professional profiles, offerings, ICPs, strategies,
repeat preferences, subscriptions, source tables and all `ops` audits/guards are
outside that deletion list. Retain a before/after comparison, not just deleted counts.

## Apply explicit setup in order

Bring existing account/lifecycle and execution-guard prerequisites to the supported
layout using the [schema guide](../db/schema/README.md). Do not rerun the destructive
base bootstrap against an existing database or recreate its volume.

For an existing management database, the legacy container tables are prerequisites
for repeatable ownership setup. They have no active batch writer in the new code:

```sh
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/schema/operational-recommendations.sql \
  -f db/schema/operational-weekly-digest.sql \
  -f db/schema/operational-business-ownership.sql
```

Read configuration and consent back before proceeding. Ownership setup preserves
existing IDs, values, associations, opt-out and repeat intervals; it creates missing
Business fields unset rather than copying personal information.

Only after target inspection, authorization and writer quiescence, apply:

```sh
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/schema/operational-obsolete-prospecting-cleanup.sql
rtk proxy psql "$HUGINN_MANAGEMENT_DATABASE_URL" -v ON_ERROR_STOP=1 \
  -f db/schema/operational-prospecting.sql \
  -f db/schema/operational-weekly-digest-content.sql
```

Each file owns its transaction. Cleanup locks its enumerated tables, checks active
work and new history, temporarily disables only known enabled legacy immutable-delete
guards, deletes children before parents and restores those guards. Unexpected schema,
foreign-key dependencies or unresolved work roll back the transaction. An already
empty target deletes no rows. Once any new recommendation, receipt, block, prospect,
offer or delivery history exists, cleanup refuses replay, including a new reservation
that has not yet acquired content.

The content setup removes legacy batch-based delivery columns only from an empty
delivery table. It creates immutable content versions, exact revision/cycle members,
delivery events and guarded state transitions. It does not rewrite old email content
into the new representation.

Fresh empty-volume Compose initialization applies the canonical schema in dependency
order. It never invokes obsolete-workflow cleanup. Normal application startup and
HTTP reads apply no DDL, cleanup, source reconciliation or backfill.

## Reconcile and verify guarded readers

Install the source-currentness and guarded-evidence setup described in the
[source-currentness guide](source-currentness.md). Audit and explicitly reconcile
each retained source after relevant Bronze/Silver/Gold materialization. For example:

```sh
rtk proxy uv run python -m huginn.elt.silver.presentation.cli.source_currentness audit \
  --source yc --summary .local-runtime/currentness/yc-audit.json
rtk proxy uv run python -m huginn.elt.silver.presentation.cli.source_currentness reconcile \
  --source yc --summary .local-runtime/currentness/yc-reconcile.json
```

Repeat for supported `hn` and `eu_startups` sources as applicable. Inspect aggregate
results and exact retained evidence lineage. Reconciliation is not an upstream fetch;
stale or missing evidence remains unavailable rather than falling back to raw Gold.
The existing pipeline performs relevant reconciliation after materialization on
subsequent runs.

Start the new application with new discovery work still disabled. `/health` is
liveness. `/ready` performs bounded read-only probes of account/configuration,
guarded evidence and new recommendation/prospect/delivery schema, including the
cycle-backed weekly layout. Readiness does not assert that all upstream records have
been reconciled or that any Company is eligible; inspect the source audit separately.

Verify retained account/configuration/consent/source/audit rows match the baseline.
Exercise owner isolation, exact historical reads and authorized management actions on
the disposable rehearsal target. New generation, offer preparation and confirmation
must return private 503 responses while disabled; the scheduled composition must
refuse new work without opening a database connection.

After the authorized deployment checks pass, enable new work by setting the flag to
`true` and restarting the relevant processes. Restore only the intended collection
and weekly schedules. Preserve existing opt-ins; do not bulk-enroll users. Use the
[weekly digest guide](weekly-digest.md) for dry runs, limits and explicit delivery.

## Roll back by disabling new work

Set `HUGINN_DISCOVERY_NEW_WORK_ENABLED=false`, restart the new web process and stop
scheduled digest invocations. Already authorized SMTP may still complete; the flag
does not promise recall. Preserve its actual settlement or Unknown protection.

Keep the new schema and history. Retained reads and explicit Save, Not Relevant,
pause management, prospect edits and owner-attributed delivery recovery remain
available. Do not replay cleanup, reset tables, change consent, clear independent
blocks or redeploy an old selector that ignores suppression. The retired Match
CLI/worker/admission paths remain retired. Fix forward against the preserved
recommendation/revision/cycle identities before enabling new work again.
