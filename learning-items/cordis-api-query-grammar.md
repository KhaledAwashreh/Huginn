# CORDIS API's async bulk-extraction job flow and undocumented query grammar

Status: Backlog
Surfaced: 2026-09-05
Jira: KAN-13

## Why this came up

CORDIS (EU research/innovation funding data) is a deferred future source for
an EU-funding hiring/growth signal, researched briefly for access shape.

## What this is about

Free, API-key authenticated, but not a live query endpoint: the flow is
submit a bulk-extraction job, poll for completion, then download the
result. The query grammar for filtering that bulk extract isn't documented
anywhere found during the initial research pass.

## Closest Java/C# equivalent

The submit-poll-download shape itself is a common async-job pattern in any
ecosystem (a Java `Future` being polled, or any cloud provider's long-running
batch-job API); nothing CORDIS-specific carries over, only the general
pattern.

## Key concepts to learn

1. Empirically probe the API: submit a few small test jobs and inspect what
   filter parameters actually change in the result, since the grammar isn't
   documented.
2. What the realistic latency is for the submit-poll-download cycle, this
   affects whether CORDIS could ever fit a daily polling cadence at all.

## Resources

1. `docs/sources/cordis-api.md`.

## Notes

Deferred source, low priority, revisit only if EU-funding signal becomes
worth pursuing as a phase-2+ source.
