# EU-Startups Implementation Progress

## 2026-09-22: Bronze web-scrape persistence

The raw-store path for `bronze.web_scrape_ingest` is implemented and verified.

1. `PostgresWebScrapeIngestRepository` owns parameterized SQL for hash lookup,
   insert/update, and last-checked touch operations.
2. `PostgresWebScrapeIngestStore` applies the existing content-hash semantics
   in one transaction per batch.
3. The store rejects a repository for any Bronze table other than
   `web_scrape_ingest`.

The `eu-startups-discovery` CLI command wires the EU discovery adapter through
its dedicated transactional runner.

## 2026-09-30: Atomic discovery checkpoint

The EU discovery commit now atomically persists records, retries, and its
durable checkpoint.

1. EU discovery returns a `DiscoveryBatch` containing successful raw records,
   an advisory proposed watermark, and failed listing outcomes.
2. `PostgresEuStartupsDiscoveryRepository.commit_batch()` persists Bronze
   rows, retry state, and the durable watermark in one transaction.
3. A transaction-scoped advisory lock serializes overlapping discovery
   commits.
4. Durable retry rows replay independently of the watermark, so later
   successful listings can advance the checkpoint without losing failed URLs.

The dedicated repository owns `bronze.web_scrape_ingest`, the source
watermark, and per-URL failure state. This deliberately does not change the
shared `IngestionService` contract; HN, YC, and OpenCorporates remain on
`SourcePort.fetch() -> list[RawRecord]`.

Confirmed terminal-failure policy:

1. A current `404` or `410` outcome becomes terminal after at least three
   failed fetch attempts for the same `lastmod`.
2. A newer `lastmod` resets the attempt cycle.
3. Transient network and server failures remain retryable.

## 2026-09-30: Silver-to-Gold pipeline wiring

The EU discovery-to-Gold wiring is complete.

1. `silver.eu_startups_listings` and its Postgres repository load parsed
   directory listings from `bronze.web_scrape_ingest`.
2. Cross-source resolution reads EU-Startups alongside HN and YC; the generic
   Gold writers materialize resolved listings into `gold.company` and
   `gold.company_signal`.
3. `python -m huginn.elt` runs EU discovery, staging, resolution, and Gold in
   dependency order.

Shared resolution intentionally requires every current staging loader under
ADR-0014. Source isolation would require a separate design change.

## 2026-10-01: Company-name enrichment runner

Company-name enrichment is wired as a separate bounded workflow.

1. `EuStartupsEnrichmentAdapter.fetch_batch()` returns raw detail records and
   one outcome per candidate name. Definitive outcomes advance
   `eu_startups_searched_at`; network failures, possibly truncated search
   pages, detail fetch failures, and structurally invalid detail pages remain
   eligible for retry. HTTP-success detail responses must contain the expected
   single-listing title structure before they can replace Bronze data.
   `fetch()` retains its prior `list[RawRecord]` contract.
2. `PostgresEuStartupsEnrichmentRepository` stores successful raw pages and
   marks every Gold row with a definitive candidate name in one transaction.
   It hashes only `url` and `html`, touches unchanged rows, and preserves a
   stored observation whose `lastmod` is newer than the enrichment observation.
3. `EuStartupsEnrichmentRunner` records `ops.job_runs`, and the explicit
   `python -m huginn.elt.ingestion eu-startups-enrichment` command uses a
   50-name bound. After it succeeds, the command materializes EU staging
   through EU-only Silver resolution and shared Gold writers (see below).

The 32,763-listing historical discovery backfill remains a separate
operational decision. The live EU discovery watermark and historical crawl
scope must not be changed as part of enrichment wiring.

## 2026-10-01: Enrichment through Gold

The explicit enrichment command materializes EU staging through shared Gold
writers after the bounded enrichment runner commits its Bronze records and
definitive-name checkpoints.

1. `silver.eu_startups_staging`
2. `silver.signal_resolution`
3. `gold.company`
4. `gold.company_signal`

1. The enrichment runner owns the workflow's fetch/persist `ops.job_runs` row.
   Each downstream stage uses the existing stage-runner job records. A fetch
   or persist exception stops the command before any downstream stage is
   built or run; downstream stage failures produce a non-zero command exit.
   The command does not run HN or YC ingestion, nor does it run EU discovery.
2. The enrichment command uses `SignalResolver.resolve_eu_startups()`. It reads
   and upserts only EU staged/resolved signals, so an EU enrichment run cannot
   rewrite HN or YC resolution state. The full `python -m huginn.elt` pipeline
   continues to use `resolve_all()` for cross-source resolution.
3. Gold field ownership remains unchanged: YC signals supply country and city.
   EU-Startups `category` and `based_in` are not mapped into those fields, and
   EU tags are not mapped to YC-owned `business_sector`.

### Live verification

The completed workflow was exercised against the local Docker PostgreSQL
database after a full HN/YC/EU pipeline run.

1. YC populated 3,509 Gold countries and 3,470 Gold cities.
2. A bounded 50-name enrichment batch produced 47 definitive outcomes, three
   retryable truncated searches, and one exact match (`cortex`).
3. EU Bronze and Silver increased from 98 to 99 rows.
4. EU-only resolution produced 94 domain-normalized and five unresolved rows;
   `gold.company_signal` contained 94 EU signals afterward.
5. Country and city counts were unchanged by EU materialization.
6. Enrichment, EU staging, EU-only resolution, Company, and CompanySignal job
   runs all succeeded.
7. The EU discovery watermark remained `2026-09-17T10:06:57+00:00`.
8. Repository validation after the workflow change passed 787 tests, Ruff lint,
   Ruff format checking across 204 Python files, bytecode compilation, and
   `git diff --check`.
