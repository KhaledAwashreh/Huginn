# LLM-based extraction (Firecrawl/Apify extract) as a self-healing fallback for HTML-scraping sources

Status: Backlog
Surfaced: 2026-09-05
Jira: KAN-14

## Why this came up

Documented as a 2026 pattern worth having in the toolkit while researching
pipeline standards, relevant to any future HTML-scraping adapter (VC
portfolio boards, Ramp vendor reports are the two candidate sources that
would actually need it).

## What this is about

LLM extraction means feeding a page plus a natural-language schema to a
model and getting structured JSON back, instead of CSS-selector scraping.
It's genuinely more resilient to layout changes than selectors, but costs
more per page and is slower. Current guidance is consistent: use it as a
fallback when selectors break, not as the primary steady-state extraction
path for a daily pipeline.

## Closest Java/C# equivalent

None, this is a 2026-era technique enabled by LLMs specifically, not a
language or ecosystem pattern that predates it.

## Key concepts to learn

1. How Firecrawl's and Apify's "extract" endpoints actually work in
   practice, request shape, cost per page, latency.
2. How to wire "selector breaks (detected via a schema-drift check, see the
   Pandera learning item) then fall back to LLM extraction, then alert
   either way" into a future HTML-scraping adapter.

## Resources

1. `architecture-notes/data-pipeline-standards.md`, "What's new or changed
   recently" section.
2. Firecrawl and Apify's own `/extract` documentation.

## Notes

Related: `pandera-schema-validation.md` is the detection half of this
fallback pattern, this item is the recovery half.
