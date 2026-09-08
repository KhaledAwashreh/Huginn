# VC portfolio boards as a future source: Getro (Index Ventures) vs. bespoke adapters

Status: Backlog
Surfaced: 2026-09-05
Jira: KAN-10

## Why this came up

VC portfolio boards (Sequoia, a16z, Index Ventures, Greylock) are a deferred
future source. The original assumption, "one adapter covers all four,"
turned out wrong once actually checked.

## What this is about

Only **Index Ventures** actually runs on Getro, a VC-platform-team product
with 700+ customers reportedly. Sequoia uses a different vendor ("Consider").
a16z and Greylock are custom apps with no discovered API at all. Greylock's
`robots.txt` explicitly blocks `ClaudeBot` by name, a real, specific
constraint on any Claude-Agent-SDK-based crawler for that one site.

## Closest Java/C# equivalent

None, this is source-specific web research, not a programming concept.

## Key concepts to learn

1. Getro's actual API/data shape, enough to build one real adapter for Index
   Ventures specifically.
2. Whether Sequoia's "Consider" platform has any comparable programmatic
   access at all.
3. Whether the bespoke-adapter cost for the remaining boards (a16z,
   Greylock, and Consider if it turns out to have no API) is worth paying at
   all, versus just dropping this source entirely.

## Resources

1. `docs/sources/vc-portfolio-boards.md`.

## Notes

