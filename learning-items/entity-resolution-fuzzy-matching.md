# Entity resolution: fuzzy matching (Jaro-Winkler + Jaccard) and when to graduate to Splink/dedupe

Status: Backlog
Surfaced: 2026-09-05
Jira: KAN-4

## Why this came up

Huginn's MVP entity resolution is locked as a design decision (domain-as-canonical-key
first, then a fuzzy-match fallback), but the fallback itself was researched and
adopted via Claude, not personally verified. No background in entity resolution
existed to check it against, so it was explicitly accepted as technical debt.

## What this is about

The fallback, when two records don't share a normalized domain: strip legal
suffixes (OpenSanctions suffix list) then run Jaro-Winkler string similarity
(~0.92 auto-match, ~0.85-0.92 manual-review band, below that no-match) plus
token-Jaccard similarity to catch word-order variance ("Acme Robotics" vs.
"Robotics Acme Inc"). Ambiguous scores go to a manual-review queue rather than
an automatic decision.

## Closest Java/C# equivalent

Not language-specific, the algorithms exist as libraries in both worlds:
Apache Commons Text's `JaroWinklerSimilarity` in Java, or FuzzySharp in .NET.
The concept transfers directly, only the specific library differs.

## Key concepts to learn

1. How Jaro-Winkler actually computes a score, not just what the threshold
   numbers mean, prefix weighting and transposition counting specifically.
2. How token-Jaccard differs from Jaro-Winkler and why both are needed
   (one catches typos/spelling drift, the other catches reordering).
3. Full probabilistic record linkage tools, Splink, `dedupe`, Zingg, and
   the actual trigger for switching to one: they need real data volume or a
   labeled-pair backlog to train against, not justified at MVP scale.
4. What OpenSanctions' legal-suffix reference data actually is and how to
   pull it.

## Resources

1. `architecture-notes/data-pipeline-standards.md`, "Entity resolution at
   small scale" section.
2. Splink docs, `dedupe` docs (Python, the active-learning labelling loop is
   the interesting part).

## Notes

Trigger to prioritize: once the manual-review queue accumulates a real
backlog of ambiguous matches worth training against.
