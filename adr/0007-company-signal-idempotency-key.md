# 0007: gold.company_signal gets a (source, source_stable_id) natural key

Status: Accepted
Date: 2026-09-17
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting, autonomous overnight run per explicit authorization, KAN-41)

## Context and Problem Statement

KAN-41 asks for a writer that inserts one `gold.company_signal` row per
`silver.resolved_signals` row. `db/schema/gold.sql`'s current
`gold.company_signal` definition has no column identifying which source
signal produced a given row, and no unique constraint beyond its own
generated `id`. `SignalResolver.resolve_all()` (Silver) reprocesses and
rewrites every staged signal on every run, by design (its own docstring:
"the write executes on every row even when nothing changed"). A writer that
reads `resolved_signals` and does a plain `INSERT` into `company_signal`
with no natural key would insert a duplicate fact row for the same
underlying signal on every single ingestion pass, forever. This was not
named or resolved in KAN-41's ticket text, which only says "write one row
per resolved_signals row" without addressing rerun behavior.

## Decision Drivers

1. Every other writer in this pipeline treats "safe to rerun without
   duplicating" as a first-class concern: Bronze's content-hash watermark,
   Silver's `(source, source_stable_id)` `UNIQUE` upsert key on
   `resolved_signals` itself, and Gold's own `Company` writer upserting on
   `domain`. A fact writer with no equivalent key would be the one
   exception in the whole pipeline, not a deliberate design choice, an
   oversight the ticket's own text didn't address.
2. `resolved_signals` already carries a natural key that maps 1:1 to a
   single real-world event: `(source, source_stable_id)`. Reusing it on
   `company_signal` needs no new identifier scheme, and keeps every layer
   in this pipeline traceable back to the same originating signal by the
   same two columns.
3. `resolved_signals` rows can change in place (an HN/YC posting re-fetched
   with an edited description, a corrected `stage`), and `company_signal`
   should reflect that, matching how `Company` reflects the latest resolved
   state rather than freezing the first-seen values.

## Considered Options

1. Add `source_stable_id` to `gold.company_signal`, with `UNIQUE (source,
   source_stable_id)`, and upsert on that key (`ON CONFLICT ... DO UPDATE`).
   (chosen)
2. Leave the schema as-is; make the writer read-then-check (query for an
   existing row matching signal content before inserting) instead of a
   database-enforced constraint.
3. Leave the schema and the writer both as specified literally in the
   ticket (a plain `INSERT` per row), and accept duplicate rows as a known
   limitation for a future ticket to fix.

## Decision Outcome

Chosen option: 1, a `UNIQUE (source, source_stable_id)` constraint plus an
upsert. Option 2 (application-side existence check) duplicates work Postgres
already does better and race-condition-free via `ON CONFLICT`, and every
sibling writer in this codebase (`resolved_signals`, `gold.company`) already
uses a database constraint for exactly this, not an application-side check.
Option 3 (accept duplicates) is not a real option: `resolve_all()`'s
documented every-run-reprocessing behavior means this is not a rare edge
case, it is the normal, expected behavior of a second ingestion run,
something this project has already run in practice (the 6,253-signal batch
KAN-62 and KAN-67 cite).

### Consequences

1. Good: `CompanySignalWriter` is idempotent and safely re-runnable, like
   every other writer in this pipeline.
2. Good: no new identifier scheme, reuses `resolved_signals`'s own natural
   key.
3. Good: an edited upstream signal's `company_signal` row reflects the
   latest content on the next run, rather than freezing stale data forever.
4. Neutral: `db/schema/gold.sql` changes before any other code depends on
   its current shape (no migration tooling exists yet, KAN-49 tracks that
   as separate debt; editing the schema file directly, as every prior
   change to these files has done, is the established practice here, not a
   new one this ticket introduces).
5. Bad: `ingested_at`'s semantics now matter more than they did in a plain-
   insert design. Decided here explicitly: `ingested_at` is set once, on
   first insert, and never touched by the `ON CONFLICT` update branch (same
   pattern `gold.company`'s `created_at` already uses), so it keeps meaning
   "first time this signal produced a fact," not "last time this row was
   touched."

## Pros and Cons of the Options

### Option 1: unique key + upsert (chosen)

1. Good: idempotent, race-condition-free, consistent with every sibling
   writer in this codebase.
2. Good: minimal schema change, one column and one constraint.
3. Bad: a schema change to a table this ticket didn't originally expect to
   touch, needs this ADR so a future reader understands it was deliberate.

### Option 2: application-side existence check

1. Good: no schema change.
2. Bad: a check-then-act race between two concurrent runs (not impossible,
   `resolve_all()`'s docstring already discusses future concurrent-write
   races on the same table).
3. Bad: an extra read per row this writer doesn't otherwise need, when the
   database can enforce the same guarantee for free as part of the write.

### Option 3: accept duplicates as known debt

1. Good: zero implementation cost now.
2. Bad: `gold.company_signal` would grow without bound on every ingestion
   run at real project volume, corrupting any downstream count/aggregate
   built on it (a company's signal history, "how many hiring posts this
   quarter") from the very first rerun, not a scale problem for later.

## Related

1. `db/schema/silver.sql`'s `resolved_signals.(source, source_stable_id)`
   `UNIQUE` constraint, the key this ADR reuses.
2. `src/huginn/elt/gold/repositories/company_repository.py`'s
   `build_upsert_query`, the same `ON CONFLICT ... DO UPDATE` pattern this
   ADR's writer follows for `gold.company_signal`.
3. Jira KAN-40 (Company writer, the sibling writer this pattern-matches),
   KAN-41 (this decision's ticket), KAN-49 (no migration tooling, the
   reason this ADR edits `db/schema/gold.sql` directly rather than writing
   an `ALTER TABLE` migration file).
