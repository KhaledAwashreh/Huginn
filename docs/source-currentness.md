# Source lifecycle observations

Audit stored Bronze records and explicitly preserve their lifecycle and identity
transitions. This extends [source-context preservation](source-context.md).
Current-signal endpoints use a guarded source-context projection. Match list and
detail reads retain durable history and report current/historical source-evidence
availability separately. Matchmaking selects guarded observations within the
original source-event window and captures their immutable IDs only for newly
created Matches. Source availability does not establish consulting demand or
current ICP fit on its own.

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

For HN comments without paragraph boundaries, only the first normalized line
is treated as the closure header. A `CLOSED NOW` status there withdraws the
listing; a status on a later line does not. A paragraph-only comment has an
empty header, so this closure rule does not withdraw it.

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
rtk proxy uv run python -m huginn.elt.silver.presentation.cli.source_currentness audit --source yc --summary .local-runtime/currentness/yc-audit.json
```

Reports contain aggregate states, reasons, selected counts, and a fingerprint
of selected raw/resolution versions. `--limit 100` selects the first 100 stored
stable IDs and labels the report as a limited sample. It does not estimate
full-source coverage. Reports contain no source text or credentials.

Library callers import audit/reconcile services from
`huginn.elt.silver.services.source_currentness`. To write a summary file, pass a
`JsonReportWriter` implementation explicitly; the CLI composes the filesystem
adapter. Parsing and lifecycle decisions remain independent of database,
network and file-output implementations.

Before reconciliation, back up and inspect the target's schema. Existing
databases need `silver-source-context.sql` first if its tables are absent.
Both fresh and existing databases then apply the same canonical migration
after the Bronze, Silver, Gold, and operational base schemas:

```bash
rtk proxy psql "$HUGINN_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/silver-source-currentness.sql
rtk proxy uv run python -m huginn.elt.silver.presentation.cli.source_currentness reconcile --source yc --summary .local-runtime/currentness/yc-reconcile.json
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
Guarded readers require the additional migration below. Retain the guards and
history during rollback; restoring an unguarded current-context endpoint would
reintroduce stale evidence.

## Guarded current context and retained Match history

After the base and lifecycle schemas, apply the same additive reader migration
on fresh and existing databases:

```bash
rtk proxy psql "$HUGINN_DATABASE_URL" -v ON_ERROR_STOP=1 -f db/schema/gold-current-source-evidence.sql
```

The migration creates `gold.current_source_evidence` and
`operational.match_source_evidence`. It does not reconcile records or backfill
legacy Match evidence. Readiness requires both objects. Prepare and verify the
schema, audit/reconcile explicitly, then deploy guarded readers; missing or changed
source observations stay unavailable until reconciled. Never run this sequence
against a shared database without reviewing the exact target and dry-run impact.

The view checks full raw and resolution tokens, current source and parser policy,
snapshot identity, available listing, consistent identity, Gold signal company
association, and the current company domain. Unsupported sources have no legacy
fallback. `last_checked_at` alone does not invalidate unchanged content. A current
pointer is insufficient when the underlying raw input or company association has
changed since reconciliation.

Displayed descriptions, URLs, stages and event times come from preserved source
context and lifecycle observations. Gold supplies the compatible signal ID and
its original ingestion metadata; that ingestion time is not proof of source
freshness. HN and affirmative YC hiring claims are labelled hiring context. YC
false/unknown hiring and EU listings are directory context, not fabricated
milestones. Missing event time stays null and is displayed as unknown.

Match list/detail records, workflow status, notes and durable `has_matches` remain
accessible even when current evidence disappears. `current_source_evidence_available`
reports whether guarded context exists for the company. It does not mean the
company still qualifies for the user's ICP. `historical_evidence_available` reports
stored creation-evidence links only, independently of current pointers or mutable
Gold signals. Existing Matches without those links report false; today's source
association is never presented as their creation history. A failed UI refresh
marks cached source context as previously received and currently unverified.

Snapshots and stored evidence links reject update/delete. A Match cannot change
its ID, owner or company; status and notes remain editable. Link
insertion requires the exact guarded observation, its captured context and matching
company, with source event time in the original inclusive matching window. These
checks use the inserting transaction's consistent snapshot. They do not guarantee
freshness against ingestion committed after that snapshot.

Matchmaking uses this view with its existing ICP/exclusion filters and inclusive
source-event window. It preserves the existing any-kind prospecting rule,
including directory context, while rejecting stale or unreconciled sources.
Selected observation IDs survive the per-company strategy union and are inserted
with the original window in the same transaction as a newly created Match.
Existing or conflicting Matches receive no evidence backfill. Every tentative
Match/link for a User rolls back together on failure; retries retain the original
window and discard evidence from the failed attempt. See [matchmaking.md](matchmaking.md)
for runtime grants and operator behavior. Company/ICP state and ranking results
are not snapshotted by this source-evidence capture.

The separate [attribute assessment](attribute-assessment.md) reads guarded
snapshots to propose missing company attributes and compare synthetic matching
results. It is read-only and keeps country-alias effects separate from field
fills; it does not deploy schemas, change company attributes or create Matches.

## Explicit HN header closure

Lifecycle policy `source-lifecycle-v2` withdraws an HN listing when a dedicated
pipe-delimited status segment on the first header line says `CLOSED NOW`,
optionally followed by punctuation or an explanation after a dash or colon.
Body-only closure mentions, negations and closure words inside names or URLs do
not trigger this rule. It is deliberately narrow and does not recognize every
possible way a poster can announce closure.

The complete source text and source-event timestamp remain preserved. Closure
applies to that listing; it does not disqualify the company or erase historical
Match evidence. A closed header takes precedence over an older application
invitation remaining in the body. This status requires a successful fresh fetch;
a changed upstream post cannot be detected from an unchanged Bronze payload.

The guarded view expects policy v2 for all sources, matching the shared lifecycle
policy version. Apply the reviewed `gold-current-source-evidence.sql` view update
and explicitly reconcile source observations under v2 as part of a deployment.
After the view update, v1 observations remain history but cannot qualify as
current evidence. Reconciliation must precede resuming guarded readers. No
persistent deployment or reconciliation runs automatically from this code change.
