# EU-Startups Implementation Progress

## 2026-09-22: Bronze web-scrape persistence

Implemented and verified the raw-store path for `bronze.web_scrape_ingest`:

- `PostgresWebScrapeIngestRepository` owns parameterized SQL for hash lookup,
  insert/update, and last-checked touch operations.
- `PostgresWebScrapeIngestStore` applies the existing content-hash semantics
  in one transaction per batch.
- The store rejects a repository for any Bronze table other than
  `web_scrape_ingest`.

The EU discovery adapter is intentionally not wired into the CLI yet.

## Next: atomic discovery checkpoint

Do not persist `DiscoveryWatermarkPort.save_watermark()` as currently called
by `EuStartupsDiscoveryAdapter.fetch()`: it advances before the raw records
are stored. Redesign the discovery result and orchestration boundary so Bronze
writes, retry state, and watermark advancement commit atomically.

Selected implementation boundary: EU discovery returns an explicit
`DiscoveryBatch`, containing successful raw records, the proposed watermark,
and failed URL outcomes. A dedicated EU discovery repository reads the prior
watermark and persists the batch in one transaction. It owns three concerns:
`bronze.web_scrape_ingest`, the source watermark, and per-URL failure state.
This deliberately does not change the shared `IngestionService` contract;
HN, YC, and OpenCorporates remain on `SourcePort.fetch() -> list[RawRecord]`.

Confirmed terminal-failure policy: after three failed fetch attempts, a
confirmed `404` or `410` listing becomes terminal. Transient network and
server failures remain retryable.

After that: implement the Silver EU table/repository/loader, then wire the
discovery and enrichment workflows into an executable composition root.
