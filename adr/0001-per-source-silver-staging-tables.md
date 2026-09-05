# 0001: Per-source Silver staging tables, despite identical schemas

Status: Accepted
Date: 2026-09-05
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting)

## Context and Problem Statement

Silver's staging layer conforms each source's Bronze payload into a common shape before entity resolution runs. `HnPostingStaging` and `YcListingStaging` have identical column lists: `StableId`, `CompanyNameRaw`, `Website`, `SignalType`, `Stage`, `Description`, `OccurredOn`, `Url`, `IngestedOn`, `UpdatedOn`.

This reads as unjustified duplication. A single shared table with a `Source` column would carry the same information with less repetition, and that is exactly the design Bronze already uses: `bronze.api_ingest`, `bronze.web_scrape_ingest`, and `bronze.newsletter_ingest` each hold multiple sources behind a `Source` column. Without the reasoning below, the inconsistency between Bronze's approach and Silver's reads as a mistake, not a decision. That is why this needed writing down.

## Decision Drivers

1. Blast radius of an operational mistake (a bad migration, a scoped `DELETE`, an ad hoc backfill) should be contained to one source, not depend on someone remembering a `WHERE Source = ...` filter.
2. A bug in one source's transform or adapter code should not be able to write a row that looks like it came from another source.
3. A source-specific staging need in the future (a raw confidence score, an extra provenance field) should not force a schema change touching every other source's rows.
4. Each source's staging output should be checkable in isolation, without filtering out other sources' noise first.
5. Physical duplication of identical DDL is a real cost. It needs an actual reason, not habit.

## Considered Options

1. One staging table per source (chosen)
2. One shared staging table across all sources, disambiguated by a `Source` column. Mirrors Bronze's mechanism-grouped design.

## Decision Outcome

Chosen option: 1, one staging table per source. Silver is where a source's data first gets typed and given real column-level meaning. Bronze's payloads are opaque JSON, so merging sources behind a `Source` column costs nothing structurally there. At Silver, a shared table means every operational query, migration, and fix needs a correct filter to stay scoped to one source. Miss it once and every source's data is exposed to the mistake. Per-source tables make that class of error impossible instead of relying on discipline.

### Consequences

1. A migration or ad hoc fix cannot leak across sources through a missing filter. The table boundary enforces it.
2. A transform bug in one source's adapter cannot cross-contaminate another source's rows. There is no shared table for it to write into.
3. A future source-specific staging column can be added to just that source's table, without an `ALTER TABLE` or a meaningless nullable column on every other source.
4. A source's staging output is debuggable in isolation.
5. More tables exist to create and track as sources are added. Mechanical, but real.
6. A schema change genuinely common to every source (for example, adding an `IngestRunId` column) costs one `ALTER TABLE` per staging table instead of one.

## Pros and Cons of the Options

### Option 1: One staging table per source

1. Good: operational mistakes are scoped to one source by construction, not by a `WHERE` clause someone has to remember to write correctly every time.
2. Good: each source's write path is isolated from every other source's transform bugs.
3. Good: a source can evolve its own staging schema independently, without a migration touching unrelated sources.
4. Good: parallels the ports-and-adapters isolation already used at the ingestion layer. One adapter per source, no shared ingestion state.
5. Bad: DDL duplication while the schema stays identical, which reads as redundant without this ADR's context.
6. Bad: a universally-needed schema change costs one migration per table instead of one migration total.

### Option 2: One shared staging table (mirrors Bronze)

1. Good: a single physical object. No duplicated DDL, one place to add a column every source needs.
2. Good: mirrors the pattern already adopted at Bronze, which would look more superficially consistent.
3. Bad: every operational query, migration, or fix must correctly filter by `Source` to stay scoped. A missed filter touches every source's data, not just one.
4. Bad: Silver's data is typed, not opaque JSON like Bronze's. A source-specific column has no clean home without becoming a nullable column that means nothing for every other source.
5. Bad: a bug in one source's transform logic writing into a shared table has no structural barrier stopping it from touching another source's rows.

## Related

1. `Huginn Arch Dcument.md` §4: Silver layer description.
2. `architecture-notes/elt-pipeline-and-scoring-decisions.md` §2.3: the original Silver structure decision.
3. `architecture-notes/elt-pipeline-and-scoring-decisions.md` §2.2: Bronze's mechanism-grouped shared-table design. The contrasting choice this ADR explains rather than contradicts, justified there by Bronze's schema-on-read, opaque-JSON nature.
4. `Entites.md`: the concrete staging table shapes this ADR explains.
