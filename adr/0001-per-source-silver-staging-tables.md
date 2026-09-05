# 0001 — Per-source Silver staging tables, despite identical schemas

**Status:** Accepted
**Date:** 2026-09-05
**Deciders:** Khaled Awashreh (with Claude Sonnet 5 assisting)

## Context and Problem Statement

Silver's staging layer conforms each source's Bronze payload into a common shape before entity resolution runs (`Entites.md` — `HnPostingStaging`, `YcListingStaging`). Every one of these tables has the exact same column list — `StableId`, `CompanyNameRaw`, `Website`, `SignalType`, `Stage`, `Description`, `OccurredOn`, `Url`, `IngestedOn`, `UpdatedOn`. Nothing differs.

Read cold, this looks like unjustified duplication — a single shared table with a `Source` column would carry the same information with less repetition, and that's exactly the design Bronze already uses (`bronze.api_ingest`, `bronze.web_scrape_ingest`, `bronze.newsletter_ingest` each hold multiple sources behind a `Source` column). Without the reasoning below, the inconsistency between Bronze's approach and Silver's reads as a mistake, not a decision — which is why this needed writing down.

## Decision Drivers

- Blast radius of an operational mistake (a bad migration, a scoped `DELETE`, an ad hoc backfill) should be contained to one source, not depend on someone remembering a `WHERE Source = ...`.
- A bug in one source's transform/adapter code shouldn't be able to write a row that looks like it came from another source.
- A source-specific staging need in the future (a raw confidence score, an extra provenance field) shouldn't force a schema change touching every other source's rows.
- Each source's staging output should be checkable in isolation, without filtering out other sources' noise first.
- Physical duplication of identical DDL is a real cost and shouldn't be paid for no reason — hence needing an actual reason, not just habit.

## Considered Options

- One staging table per source (chosen)
- One shared staging table across all sources, disambiguated by a `Source` column — mirrors Bronze's mechanism-grouped design

## Decision Outcome

Chosen option: "one staging table per source," because Silver is where a source's data first gets typed and given real column-level meaning — unlike Bronze, where payloads are opaque JSON and merging sources behind a `Source` column costs nothing structurally. At Silver, a shared table means every operational query, migration, and fix needs a correct filter to stay scoped to one source; miss it once and every source's data is exposed to the mistake. Per-source tables make that class of error physically impossible instead of relying on discipline.

### Consequences

- Good, because a migration or ad hoc fix can never leak across sources by a missing filter — the table boundary enforces it structurally.
- Good, because a transform bug in one source's adapter can't cross-contaminate another source's rows; there's no shared table for it to write into.
- Good, because a future source-specific staging column can be added to just that source's table without an `ALTER TABLE` (or a meaningless nullable column) on every other source.
- Good, because a source's staging output is debuggable in isolation.
- Bad, because more tables exist to create and track as sources are added — mechanical, but real.
- Bad, because a schema change genuinely common to every source (e.g. adding an `IngestRunId` column) costs one `ALTER TABLE` per staging table instead of one.

## Pros and Cons of the Options

### One staging table per source

- Good, because operational mistakes are scoped to one source by construction, not by a `WHERE` clause someone has to remember to write correctly every time.
- Good, because each source's write path is isolated from every other source's transform bugs.
- Good, because a source can evolve its own staging schema independently, without a migration touching unrelated sources.
- Good, because it directly parallels the ports-and-adapters isolation already used at the ingestion layer — one adapter per source, no shared ingestion state.
- Bad, because it's DDL duplication while the schema stays identical, which reads as redundant without this ADR's context.
- Bad, because a universally-needed schema change costs one migration per table instead of one migration total.

### One shared staging table (mirrors Bronze)

- Good, because it's a single physical object — no duplicated DDL, one place to add a column every source needs.
- Good, because it directly mirrors the pattern already adopted at Bronze, which would look more superficially consistent.
- Bad, because every operational query, migration, or fix must correctly filter by `Source` to stay scoped — a missed filter touches every source's data, not just one.
- Bad, because Silver's data is typed, not opaque JSON like Bronze's — a source-specific column has no clean home without becoming a nullable column that's meaningless for every other source.
- Bad, because a bug in one source's transform logic writing into a shared table has no structural barrier stopping it from touching another source's rows.

## Related

- `Huginn Arch Dcument.md` §4 — Silver layer description
- `architecture-notes/elt-pipeline-and-scoring-decisions.md` §2.3 — the original Silver structure decision
- `architecture-notes/elt-pipeline-and-scoring-decisions.md` §2.2 — Bronze's mechanism-grouped shared-table design, the contrasting choice this ADR explains rather than contradicts (justified there by Bronze's schema-on-read, opaque-JSON nature)
- `Entites.md` — the concrete staging table shapes this ADR explains
