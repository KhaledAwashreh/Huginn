# dlt (dlthub) as a Python ingestion library for source adapters

Status: Backlog
Surfaced: 2026-09-05
Jira: KAN-5

## Why this came up

Identified as the practical 2026 successor to hand-rolling a Singer-style tap
contract for Huginn's ports-and-adapters ingestion layer, while researching
pipeline architecture standards.

## What this is about

`dlt` is a plain importable Python library, not a separate orchestration
framework or subprocess protocol. Write a generator function, decorate it,
and get schema inference, incremental-loading primitives (a cursor/state
concept matching the Singer "bookmark" idea), and warehouse loading for
free. Reportedly ~81,000 pipelines built with it by January 2026, including
a notable share authored by AI agents rather than humans.

## Closest Java/C# equivalent

No single direct equivalent. Loosely comparable to writing a custom Kafka
Connect connector or a Spring Batch job in Java, but far lighter: a decorated
generator function instead of implementing a framework's connector interface.

## Key concepts to learn

1. dlt's actual API: decorators, generator functions, how schema inference
   works in practice.
2. How its incremental/state primitives map onto Huginn's own per-source
   content-hash watermark design, particularly for cursor-less sources like
   YC's Algolia backend, which has no native "give me only what changed" cursor.
3. Whether individual `SourcePort` adapters should become thin dlt-source
   wrappers instead of hand-rolled HTTP/pagination/retry code, and what that
   would cost or save relative to the current approach.

## Resources

1. `architecture-notes/data-pipeline-standards.md`, "What's new or changed
   recently" section.
2. dlthub's own documentation and quickstart.

## Notes

