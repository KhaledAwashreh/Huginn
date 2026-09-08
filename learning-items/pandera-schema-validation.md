# Pandera for per-adapter schema-drift validation (vs. Soda Core, Great Expectations)

Status: Backlog
Surfaced: 2026-09-05
Jira: KAN-6

## Why this came up

Recommended over Great Expectations for Huginn's scale while researching
data-quality/observability options for the ingestion pipeline.

## What this is about

Pandera is a Python-native, dataframe-oriented validation library (pandas,
and by 2026 also Polars/Dask/PySpark/Ibis): declare expected columns,
dtypes, and constraints as code, using type hints. The pitch that matters
for Huginn: if a third-party feed (HN, YC, or any future source) changes its
schema without warning, Pandera catches the discrepancy before it corrupts
downstream data, instead of a silent bad row flowing all the way to Gold.

## Closest Java/C# equivalent

Bean Validation (JSR 380, the `javax.validation` annotations) in Java, or
FluentValidation in C#: declaring the shape data must have, and getting a
validation failure instead of silently accepting malformed input. Pandera
applies the same idea to a whole dataframe's schema rather than one object.

## Key concepts to learn

1. Pandera's schema-definition API, and how to wire one schema per
   `SourcePort`'s output shape, this fits the existing hexagonal
   ports-and-adapters seams directly.
2. When Soda Core (YAML/SQL-native, not Python) would actually be the better
   fit instead, specifically if a check needs to live outside Python code.
3. Why Elementary doesn't apply here: it's dbt-native, only relevant if a
   dbt layer ever gets adopted for Silver/Gold transforms.

## Resources

1. `architecture-notes/data-pipeline-standards.md`, "Lightweight
   data-quality/observability" section.
2. Pandera's own documentation.

## Notes

