# KAN-83: EU-Startups Atomic Discovery

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development task-by-task.

**Goal:** Prevent a successful EU discovery fetch from advancing its crawl
checkpoint before its Bronze records and failure state are durable.

## Global Constraints

1. Sitemap-only discovery remains unchanged; no country-page crawling.
2. Successful records, source watermark, and failure state commit in one
   PostgreSQL transaction.
3. A confirmed HTTP `404` or `410` becomes terminal after exactly three
   failed attempts. Network and `5xx` failures remain retryable.
4. Do not change HN, YC, or OpenCorporates contracts or behavior.
5. Tests are fixture-based; database integration tests are optional when
   Postgres is unavailable.

## Task 1: Discovery batch contract

Create explicit immutable result models for successful records, proposed
watermark, and failed listing outcomes. Update the EU adapter to return that
batch without persisting a watermark. Replace current tests that assert an
adapter-side watermark write with batch assertions.

## Task 2: Transactional persistence

Add Bronze schema and a source-specific PostgreSQL repository which reads the
watermark and atomically writes successful records, updates retry state, and
advances the watermark. Add unit and integration coverage for rollback and
the three-attempt terminal rule.

## Task 3: Dedicated discovery runner

Add a small EU discovery runner that supplies the persisted watermark to the
adapter and commits its returned batch through the repository. Keep the shared
`IngestionService` unchanged. Cover a failed persistence transaction proving
the watermark does not advance.
