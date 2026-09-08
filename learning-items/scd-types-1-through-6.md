# SCD Types 1-6 and hybrid Type 1/Type 2 column-classification design

Status: Backlog
Surfaced: 2026-09-05
Jira: KAN-17

## Why this came up

Huginn's Gold layer adopted SCD Type 2 (versioned, `valid_from`/`valid_to`),
while Silver stays current-state-only. The versioning trigger is a hybrid
approach, explicitly classifying each Gold column as Type 1 (overwrite in
place, no version) or Type 2 (a change triggers a new version), confirmed as
the standard pattern for "don't version on cosmetic/noisy field changes."
Only the Type 1/Type 2 hybrid was actually needed, the broader SCD taxonomy
was never studied.

## What this is about

Slowly Changing Dimensions are a data-warehousing pattern family for
tracking how a dimension's attributes change over time. Type 1 (overwrite)
and Type 2 (new versioned row) are the two Huginn actually uses; Types 3
through 6 (including hybrid and bitemporal variants) exist for cases this
project doesn't currently have.

## Closest Java/C# equivalent

No language-level equivalent, this is a data-warehousing/SQL modeling
concept. The closest cross-ecosystem parallel is SQL Server's temporal
tables feature (system-versioned tables), which implements a Type 2-like
pattern at the database engine level rather than in application code.

## Key concepts to learn

1. The fuller SCD taxonomy, Types 1 through 6, hybrid, bitemporal, and when
   each is actually justified rather than over-engineering.
2. How tools like dbt snapshots implement Type 2 mechanically, since a
   future Silver/Gold transform layer might eventually use dbt.
3. Confirm Huginn's own Gold `company_history` implementation
   (`src/huginn/gold/dimensional.py`, ADR-0002) is a correct, deliberate
   instance of the pattern, not an accidental deviation from it.

## Resources

1. `architecture-notes/elt-pipeline-and-scoring-decisions.md` section 2.4.
2. `adr/0002-gold-current-history-split.md`, Huginn's own current-plus-history
   decision, which supersedes the original single-Type-2-table design this
   ticket's SCD research was based on.

## Notes

