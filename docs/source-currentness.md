# Source lifecycle observations

Audit stored Bronze records and explicitly preserve their lifecycle and identity
transitions. This extends [source-context preservation](source-context.md).
It does not yet change matching, current-signal endpoints, Gold materialization,
or existing Match records. Runtime reader guards and evidence at Match creation
remain separate integration work.

## Stored facts

Each observation records three independent states:

| State | Values | Meaning |
| --- | --- | --- |
| Listing | `available`, `withdrawn`, `invalid`, `unknown` | The source record's lifecycle and structural validity |
| Hiring | `true`, `false`, `unknown`, `not_applicable` | An explicit source claim, independent of listing availability |
| Identity | `consistent`, `unresolved`, `mismatch`, `missing` | Whether the current explicit website agrees with domain resolution |

YC `Inactive` and `Acquired` withdraw that listing, even when unrelated
description fields are malformed. `Active` and `Public` remain available when
context is valid. Missing or unrecognized status is unknown; explicit false
hiring remains distinct from absent or unknown hiring. Neither directory
availability nor a stored hiring claim alone establishes match qualification.

HN roots, non-comments, dead/deleted items, and empty comments are withdrawn.
Other malformed records are invalid. The hiring state describes the source's
hiring-thread context, including withdrawn records; consumers must also check
listing and identity states. A captured EU-Startups listing remains directory
context. Its free-form company status is preserved without imposing an
unverified lifecycle taxonomy.

Identity uses YC's website, HN's first website link within its header, or the
scoped EU-Startups website field. HN paragraph boundaries are recognized
case-insensitively, including attributes. Body links never supply identity.
Only existing `domain_normalized` resolution agreeing with that explicit domain
is consistent. Reconciliation makes no HTTP or DNS requests and performs no
new entity resolution. Observations may retain a prior resolved company ID
even when identity is inconsistent; consumers must check identity state before
using an association.

Event time comes from the original HN `time`, YC `launched_at`, or EU listing
`lastmod`. Missing or invalid event time stays null. Processing and checking a
record never refresh its event age. Lifecycle facts and valid event times can
survive descriptive extraction failure, with no context snapshot attached.

## Audit and reconcile

Set `HUGINN_DATABASE_URL` for the reviewed target. The CLI also reads `.env`.
Audit uses a repeatable-read, read-only transaction and requires no lifecycle
migration:

```bash
rtk proxy uv run python -m huginn.elt.silver.currentness audit --source yc --summary .local-runtime/currentness/yc-audit.json
```

Reports contain aggregate states, reasons, selected counts, and a fingerprint
of selected raw/resolution versions. `--limit 100` selects the first 100 stored
stable IDs and labels the report as a limited sample. It does not estimate
full-source coverage. Reports contain no source text or credentials.

Before reconciliation, back up and inspect the target's schema. Existing
databases need `silver-source-context.sql` first if its tables are absent.
Both fresh and existing databases then apply the same canonical migration
after the Bronze, Silver, Gold, and operational base schemas:

```bash
rtk proxy psql "$HUGINN_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/silver-source-currentness.sql
rtk proxy uv run python -m huginn.elt.silver.currentness reconcile --source yc --summary .local-runtime/currentness/yc-reconcile.json
```

The migration owns its transaction, checks existing table compatibility, and
does not backfill observations. Application startup never applies it.
Reconcile is an explicit write operation. It appends lifecycle observations,
reuses or inserts context snapshots, and updates source current pointers.
Bronze, staging, resolution, Gold and Match rows remain untouched.

Reconcile commits each record independently. A report distinguishes `created`,
`unchanged` and `stale` inputs, including partial progress after an exception.
Stale inputs and invalid listings produce a nonzero exit status. Unknown
status is an ordinary reported state. Re-audit and rerun stale inputs; an
exception is reported by type without its potentially sensitive message.
The output directory is checked before writes and reports are replaced
atomically. Reports are local receipts, not durable database run records;
forced process termination can leave committed observations without a final
report. Reruns recover through idempotent current-state comparison.

## History and concurrency

`silver.source_lifecycle_observation` is append-only; update/delete triggers
reject mutation. `silver.source_currentness` points to an observation with the
same source and stable ID. An unchanged current signature reuses its existing
observation. A → B → A produces three observations while reusing snapshot A.
Parser and policy versions participate in that signature.

The optimistic raw token is PostgreSQL `md5(payload::text)` over the full stored
JSON, independent of Bronze's selected-field `content_hash`. It is a version
comparison token, not a security hash. Context identity retains its canonical
SHA-256. The resolution token covers company key and derivation. Timestamps
such as `last_checked_at` do not invalidate unchanged evidence.

Reconciliation serializes each source key with an advisory transaction lock,
then locks Bronze, an existing resolution row, an existing resolved company,
and the current pointer in that order. It compares the selected tokens and
company ID again before writing a snapshot, observation and pointer in one
transaction. Drift returns `stale` without observation writes. Other pipeline
writers can commit after this transaction; a stored current pointer alone is
therefore insufficient for runtime recommendation eligibility. Future guarded
readers must compare against their own consistent live input snapshot.

No missing-row or collection-absence inference occurs. Partial collection does
not imply deletion. Successfully observed individual records can reconcile
independently. History begins when reconciliation observes a transition;
intermediate raw payload versions already overwritten in Bronze are lost.

Rollback stops explicit reconciliation and retains the additive history tables.
The existing runtime is unaffected by this foundation. A future guarded-reader
rollout must separately audit/reconcile before enabling guards, preserve Match
history, and retain those guards during rollback rather than restore stale
evidence eligibility.
