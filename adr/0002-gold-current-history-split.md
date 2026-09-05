# 0002: Gold uses a current-plus-history split, not a single SCD Type 2 table

Status: Accepted
Date: 2026-09-05
Deciders: Khaled Awashreh (with Claude Sonnet 5 assisting)

## Context and Problem Statement

Gold's `Company` dimension was designed as a single SCD Type 2 table: every version of a company lives in the same table, distinguished by `valid_from`, `valid_to`, an `is_current` flag, and a surrogate key that changes per version while the domain (the durable key) stays stable. This matches Kimball's canonical Type 2 definition, verified directly against the Kimball Group's own site.

The design still has a real cost. Every version of a company repeats every unchanged column. A company with 5 versions has the same `Name`, `Country`, and `Address` stored 5 times. Worse, every read that wants current state, which is every scoring and matching read, depends on remembering `WHERE IsCurrent = true`. Miss that filter once and a query silently includes stale versions, duplicating a company in scoring or corrupting an aggregate. Huginn's own ADR-0001 already rejected this exact class of risk for Bronze and Silver: relying on someone to remember a filter correctly every time, instead of making the mistake structurally impossible.

## Decision Drivers

1. Every scoring and matching read wants current state only. History reads are rare, mostly for research and debugging.
2. A single Type 2 table duplicates every unchanged column on every version.
3. A single Type 2 table puts the "forgot the filter" risk on the hot path. ADR-0001 already rejected this same risk shape for a different layer.
4. Kimball's own naming for a current-plus-history split (Type 4) is not what most sources mean by "Type 4." Kimball's Type 4 is a mini-dimension, a different pattern entirely. Wikipedia's SCD article calls the current-plus-history pattern "Type 4," which is the naming most engineers will recognize even though it is not Kimball's own usage. This ambiguity needed resolving before choosing a name to build against.

## Considered Options

1. Single SCD Type 2 table on `Company`, with `is_current` and a per-version surrogate key (previous design, ADR-0001-adjacent reasoning not yet applied here)
2. Current-plus-history split: `Company` holds one row per company always, `CompanyHistory` holds superseded versions (chosen)

## Decision Outcome

Chosen option: 2, current-plus-history split. `Company` holds exactly one row per company, overwritten in place whenever any field changes. `CompanyHistory` gets a new row only when a Type 2 tracked field changes, carrying the superseded values and the `valid_from`/`valid_to` window they were in effect. Reading current state is `SELECT * FROM Company WHERE Domain = X`, with nothing else in that table to filter out by mistake. This applies the same reasoning ADR-0001 already used for Bronze and Silver: physical separation over a filter someone has to remember.

### Consequences

1. `Company` never duplicates unchanged columns across versions. It only ever holds the current row.
2. Reading current state for scoring and matching cannot accidentally include a stale version. There is no `is_current` filter to forget.
3. `CompanyHistory` only grows for companies whose tracked attributes actually change, not for every company regardless of activity.
4. Querying a company's full history now requires reading `CompanyHistory` in addition to `Company`, instead of one table with a date-range filter.
5. `Company.Id` no longer needs to change per version, since only one row per company ever exists there. This simplifies any foreign key that references a company, at the cost of losing the ability to pin a reference to one specific historical version through that same key alone.

## Pros and Cons of the Options

### Option 1: Single SCD Type 2 table

1. Good: one table answers both "what is current" and "what was true on date X" through the same query shape.
2. Good: matches Kimball's canonical Type 2 definition exactly, with no naming ambiguity to navigate.
3. Bad: every unchanged column repeats on every version, which grows with company count and version count together.
4. Bad: the hot-path read (current state) depends on an `is_current` filter that is easy to omit, with no structural barrier if it is.

### Option 2: Current-plus-history split (chosen)

1. Good: `Company` stays exactly at "one row per company" size regardless of how much history accumulates.
2. Good: the hot-path read has no filter to forget. Reading `Company` directly is always correct.
3. Good: consistent with ADR-0001's reasoning that physical separation beats a filter convention.
4. Bad: history queries need a join or a separate read against `CompanyHistory` instead of one table.
5. Bad: the pattern's common name, "Type 4," collides with Kimball Group's own different definition of Type 4 (mini-dimension). This document calls it the history-table pattern instead, to avoid asserting a contested name as settled.

## Related

1. `Huginn Arch Dcument.md` §4 and §9: the Gold layer and data model sections this ADR revises.
2. `architecture-notes/elt-pipeline-and-scoring-decisions.md` §2.4: the original Gold grain decision, updated in place to reference this ADR.
3. `architecture-notes/industry-references-elt-medallion.md`: the Kimball Type 2 correction this ADR supersedes, and the source of the surrogate-key and hybrid Type 1/Type 2 reasoning that still applies.
4. `adr/0001-per-source-silver-staging-tables.md`: the prior decision this ADR reuses the reasoning from, physical separation over a filter someone has to remember.
5. `Entites.md`: the concrete `Company` and `CompanyHistory` shapes this ADR explains.
