# EU-Startups Implementation Progress

## 2026-09-22: Bronze web-scrape persistence

Implemented and verified the raw-store path for `bronze.web_scrape_ingest`:

- `PostgresWebScrapeIngestRepository` owns parameterized SQL for hash lookup,
  insert/update, and last-checked touch operations.
- `PostgresWebScrapeIngestStore` applies the existing content-hash semantics
  in one transaction per batch.
- The store rejects a repository for any Bronze table other than
  `web_scrape_ingest`.

The `eu-startups-discovery` CLI command wires the EU discovery adapter through
its dedicated transactional runner.

## 2026-09-30: Atomic discovery checkpoint

1. EU discovery returns a `DiscoveryBatch` containing successful raw records,
   an advisory proposed watermark, and failed listing outcomes.
2. `PostgresEuStartupsDiscoveryRepository.commit_batch()` persists Bronze
   rows, retry state, and the durable watermark in one transaction.
3. A transaction-scoped advisory lock serializes overlapping discovery commits.
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

1. `silver.eu_startups_listings` and its Postgres repository load parsed
   directory listings from `bronze.web_scrape_ingest`.
2. Cross-source resolution reads EU-Startups alongside HN and YC; the generic
   Gold writers materialize resolved listings into `gold.company` and
   `gold.company_signal`.
3. `python -m huginn.elt` runs EU discovery, staging, resolution, and Gold in
   dependency order.

The discovery-to-Gold wiring is complete. The separate company-name enrichment
path remains open:

1. Wire `EuStartupsEnrichmentAdapter` into an executable workflow with Gold
   candidate loading, Bronze persistence, and `eu_startups_searched_at` cursor
   updates.
