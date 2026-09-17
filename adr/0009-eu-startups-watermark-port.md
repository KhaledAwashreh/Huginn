# 0009: EU-Startups discovery gets its own watermark port, not StatePort

Status: Accepted
Date: 2026-09-17
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting, autonomous overnight run per explicit authorization, KAN-64)

## Context and Problem Statement

KAN-64 flags its own open question: "Bronze's only existing watermark
(`bronze/ports.py` `StatePort`, `bronze/watermark.py`) is a per-entity
content-hash dedup keyed on `(source, stable_id)`, not a crawl-level 'max
lastmod processed' cursor. Decide whether to extend `StatePort` or add a
new mechanism." `StatePort.last_hash(source, stable_id)` answers "has this
specific entity's content changed since last time," a per-row question,
already handled automatically by `RawStorePort.write()`'s hash-match skip
for every adapter regardless of source. What ADR-0008's sitemap-only
discovery needs is a different question entirely: "what is the newest
`lastmod` this adapter has already processed, across the whole sitemap,"
a single scalar per source, not one value per entity.

## Decision Drivers

1. `StatePort`'s contract (`last_hash(source, stable_id) -> str | None`) has
   no shape for a single per-source scalar; extending it to also mean "the
   crawl-level watermark" would overload one Protocol with two unrelated
   concepts (per-entity content identity vs. per-source crawl progress).
2. `RawStorePort.write()` already deduplicates at the entity level for
   every adapter automatically; the watermark's actual job is narrower and
   cheaper than that: deciding which listing URLs are worth a detail-page
   fetch *at all*, before Bronze's own dedup ever runs. Skipping the fetch
   entirely for an unchanged listing is the whole point, since the network
   cost (one HTTP request per listing) is what the watermark exists to
   avoid, not the Bronze write itself, which is already cheap.
3. `CompanyWriter`/`CompanySignalWriter` (KAN-40/41) aren't wired into any
   orchestrator yet either. This adapter doesn't need a concrete,
   Postgres-backed watermark implementation to be useful and testable now,
   matching `CLAUDE.md` code standard 2: a Protocol with zero
   implementations is normal here, not a gap to fill preemptively.

## Considered Options

1. A new `DiscoveryWatermarkPort` Protocol, keyed by `source` on both
   methods (`read_watermark(source: str) -> str | None`,
   `save_watermark(source: str, value: str) -> None`) since it lives in the
   shared `huginn.elt.ingestion.ports` module rather than being scoped to
   one adapter instance, so other future sitemap-style adapters can reuse
   it, injected at construction, no concrete implementation required by
   this ticket (matching `EnrichmentCandidatePort`'s precedent: a small,
   focused Protocol injected as a dependency, not yet backed by a Postgres
   implementation when it was first added). (chosen)
2. Extend `StatePort` with a second method for a per-source scalar.
3. No watermark at all: re-walk and re-fetch every listing's detail page on
   every run, rely on `RawStorePort.write()`'s hash-match skip to keep the
   Bronze write cheap even though the network fetch is not.

## Decision Outcome

Chosen option: 1. A new, narrowly-scoped Protocol keeps `StatePort`'s
existing contract exactly what it already is (Decision Driver 1), and
matches this codebase's own precedent for deferring a concrete
implementation until an orchestrator actually needs one (Decision Driver 3).
Option 3 was rejected: at this source's real scale (on the order of tens of
thousands of listings, growing), re-fetching every detail page every run
forever is exactly the kind of unbounded, avoidable cost KAN-62/KAN-67
already had to reckon with elsewhere in this pipeline, worth avoiding from
the start rather than shipping and revisiting under pressure later.

### Consequences

1. Good: `StatePort`'s contract stays untouched, no risk to any existing
   caller.
2. Good: the adapter is fully testable with an in-memory fake watermark
   port, no database dependency introduced by this ticket.
3. Neutral: whichever ticket eventually wires this adapter into an
   orchestrator must also decide `DiscoveryWatermarkPort`'s concrete,
   persisted implementation (a new `ops`-schema table, a row in an existing
   table, a file) and is free to choose then, with real requirements in
   hand rather than guessed now.
4. Bad: until that wiring ticket exists, the watermark is a real contract
   with no working persistence behind it, same shape of "protocol before
   implementation" gap this codebase already treats as normal, not new here.
5. Bad: `EuStartupsDiscoveryAdapter.fetch()` calls `save_watermark(...)` and
   returns its records to the caller, with nothing committing the
   watermark and the Bronze write atomically. This is a direct consequence
   of this ADR's own Decision Outcome: KAN-64's Global Constraint 4
   mandated the watermark save happen inside `fetch()` itself, decoupled
   from whatever transaction the caller uses for its later
   `RawStorePort.write()` call. If that later Bronze write fails (a DB
   outage, a constraint violation) after `fetch()` has already returned,
   the watermark has already advanced past every listing in the batch, and
   those listings are never fetched again, silently and permanently. No
   architectural fix is attempted here (no orchestrator wiring exists yet);
   resolving it is explicitly in scope for KAN-83, whoever wires this
   adapter into an orchestrator must decide then: move the watermark
   commit into the same transaction as the Bronze write, or explicitly
   accept and document at-most-once semantics.

## Pros and Cons of the Options

### Option 1: a new, source-keyed `DiscoveryWatermarkPort` Protocol (chosen)

1. Good: `StatePort`'s contract stays untouched, no risk to any existing
   caller.
2. Good: the adapter is fully testable with an in-memory fake watermark
   port, no database dependency introduced by this ticket.
3. Good: matches this codebase's own precedent (`EnrichmentCandidatePort`)
   for deferring a concrete implementation until an orchestrator actually
   needs one.
4. Bad: until a wiring ticket exists, the watermark is a real contract with
   no working persistence behind it.

### Option 2: extend `StatePort` with a second method for a per-source scalar

1. Good: no new Protocol to introduce, one port instead of two for callers
   to depend on.
2. Bad: overloads one Protocol with two unrelated concepts, per-entity
   content identity (`last_hash`) and per-source crawl progress (the
   watermark), that answer genuinely different questions.
3. Bad: every existing `StatePort` caller now carries a method it has no
   use for, coupling unrelated concerns for no benefit.

### Option 3: no watermark at all, re-walk and re-fetch every listing every run

1. Good: zero implementation cost, no new Protocol, no persisted cursor to
   manage.
2. Bad: at this source's real scale (on the order of tens of thousands of
   listings, growing), re-fetching every detail page on every run forever
   is exactly the kind of unbounded, avoidable network cost KAN-62/KAN-67
   already had to reckon with elsewhere in this pipeline.
3. Bad: `RawStorePort.write()`'s hash-match skip keeps the Bronze *write*
   cheap even under this option, but does nothing for the network *fetch*
   cost, which is what the watermark exists to avoid in the first place.

## Related

1. `huginn.elt.bronze.ports.StatePort`: the existing mechanism this ADR
   explicitly does not extend, and why.
2. ADR-0008: the sitemap-based discovery mechanism this watermark serves.
3. `src/huginn/elt/gold/ports.py`'s `EnrichmentCandidatePort`: the precedent
   for a small, focused Protocol with no concrete implementation yet at the
   time it was added, mirrored here for `DiscoveryWatermarkPort`.
4. KAN-64 (this decision's ticket).
