## Context

See proposal.md and the reviewed architecture note. Current Gold descriptions
match Silver exactly, so this change targets preservation before promotion.
The main architecture currently describes current-state-only Silver. This change
adds a narrowly scoped versioned context sidecar; it does not turn every Silver
table into a historical store. Document that exception when implementing.

Use `4cbabd8` or a verified newer integration base. Existing relevant tests are
`tests/elt/silver/test_{hn,yc,eu_startups}_staging.py` and their integration tests.
The EU adapter's existing listing selectors already expose omitted fields.

## Goals / Non-Goals

**Goals:** complete source context, repeatable provenance, and a real-data output
comparison that can reveal wrong extraction before information reaches Gold.

**Non-Goals:** modifying existing text projections, source resolution, company
attribute precedence, current match eligibility, Gold backfills, semantic models,
new offering screens, ranking, scheduling, or lifecycle mutation. Capture status
observations now; consume them for lifecycle reconciliation in the next change.

## Decisions

### Isolated sidecar and explicit commands

Add `huginn.elt.silver.context` with typed pure source normalizers, Bronze reader,
context repository, and explicit audit/capture entrypoint. Reuse existing source
helpers while protecting their legacy output with regression tests. Prefer this
over changing existing descriptions because changing them propagates directly
through Gold and existing consumers before lifecycle guards are available.

Expose `python -m huginn.elt.silver.context audit|capture` with `--source` and
optional positive `--limit`. No limit means all current rows of that source;
selection order is MD5 of source stable ID then stable ID. `audit` writes only
explicit local reports; `capture` writes only new Silver sidecar/run tables.
Use the existing `HUGINN_DATABASE_URL` configuration, never a DSN CLI argument.
Audit uses a read-only transaction and statement timeout. Neither command invokes
the pipeline, fetches sources, checks remote domains, or runs models. Do not wire
capture into normal staging until a later integration change.

### Content and observation storage

Add `silver.source_context_snapshot` and bounded run bookkeeping through additive
DDL. Snapshot fields: ID, source, stable ID, source URL, payload SHA-256,
parser_version, full normalized text, header/body spans where meaningful,
source_fields JSONB, and captured_at. Unique key is
`(source, stable_id, payload_sha256, parser_version)`.

Digest canonical full stored payload JSON (stable key ordering), not Bronze's
watermark hash, whose field subset may omit newly relevant context. Exclude
external fetch/check metadata from that digest. Every version stores its own
text; no reliance on mutable Bronze pointers for evidence offsets.

Run bookkeeping records mode/version/input fingerprint, per-source totals and
record outcomes, snapshot references, and available observation metadata. Keep
processing/capture time separate from payload timestamps and latest check time.
A latest check is not proof of the first observation date of a payload version.
Preserve earlier snapshot links when subsequent records are excluded or invalid;
do not claim they are current. There is no authoritative current-context pointer
in this phase. Lifecycle readers will consume run outcomes in a later change.

Snapshot plus successful outcome is atomic per record; interrupted runs are
incomplete. Upsert uniqueness makes reruns safe. Invalid records get explicit
outcomes, not placeholder evidence. A run reports full success only if all its
selected inputs have nonfailure outcomes. Rollbacks must not affect legacy rows.

### Source extraction contracts

- HN: strip HTML safely, preserve visible header and body with normalized
  newlines and Unicode character offsets. Do not silently drop header text when
  `<p>` is absent. Retain outgoing href plus visible anchor text as source
  context, not resolved employer identity. Roots/dead/deleted/empty input is
  excluded with precedence documented and tested.
- EU: target listing-specific selector containers. Keep descriptions separately;
  preserve raw category/place/tag wording and existing founded/funding/status.
  No global `get_text()` over entire page; no country/sector inference.
- YC: preserve short and long descriptions, exact source collections and values,
  including false hiring, zero team size, and disqualified status. Null/missing
  optional values remain unknown. Validate types and report malformed supplied
  fields; do not silently coerce strings into booleans or fabricate dates.

Source normalizers return typed values and outcomes. Persistence adapts them to
JSONB. Use existing frozen dataclasses, Protocols, psycopg, and BeautifulSoup;
no additional NLP or database extension is required.

### Output acceptance loop

1. Add failing tests for observed omissions and adversarial near-cases.
2. Implement one source normalizer and run its tests.
3. Audit all current stored records read-only, with selected full-text examples.
4. Reproduce each discrepancy as a sanitized regression fixture. Classify it as
   implementation defect, malformed input, intentional exclusion, or source gap.
5. Fix defects and rerun tests plus the same fingerprinted audit corpus. Separately
   run a fresh deterministic holdout sample; do not tune only on known examples.
6. Repeat until no unexplained accounting or required-field loss remains. Unknown
   source facts stay unknown; do not lower acceptance criteria to hide failures.

Acceptance: every selected input accounted for; repeated identical inputs produce
identical normalization; zero unexplained missing supported fields; complete HN
visible header/body preservation; no EU boilerplate leakage in reviewed examples;
exact false/unknown/zero distinction; unchanged legacy projections/state. Report
remaining malformed records individually by safe ID/reason. These are correctness
criteria, not semantic accuracy or service-opportunity success metrics.

## Risks / Trade-offs

- Versioned context grows storage: capture only source text/context needed here;
  no raw-HTML duplication, no automatic historical deletion. Retention policy is
  deferred until usage is measured; snapshots are not claimed to recover past raw
  versions already overwritten.
- Source helpers shared with ingestion can change hashes/behavior: add legacy
  regression tests and avoid changing raw watermarking or adapter contracts.
- Live data changes during comparison: use a consistent audit read snapshot and
  report input fingerprints; parse outside long-lived DB scopes after bounded reads.
- Data mutation risk: audit enforces read-only at the database connection; capture
  requires explicit command and only new tables. Never use generic full pipeline
  commands for preservation validation.

## Migration Plan

Add canonical sidecar DDL to the Silver bootstrap plus an idempotent migration
that checks compatible existing table/constraint shape and fails on mismatches.
Test fresh bootstrap, repeat migration, incompatible-schema failure, transactional
rollback, and rerun capture in disposable PostgreSQL. Rollback disables commands
and retains additive tables; it does not drop history or alter legacy schema.

The implementation can be verified using read-only persisted input and disposable
output. Applying migrations or capture to the persistent database is a separate
reviewed operation with an exact target, dry-run counts, and rollback plan. Gold
promotion and source-state reconciliation are expressly not part of that operation.
