# Task 1 Report: Discovery Batch Contract

## Outcome

Implemented the EU-Startups discovery batch boundary without changing shared
ingestion services, database schema, repositories, or runners.

- Added frozen `DiscoveryBatch` and `FailedListingOutcome` models.
- Changed `EuStartupsDiscoveryAdapter.fetch(watermark)` to return successful
  raw records, an ISO-8601 proposed watermark, and failed listing outcomes.
- Removed adapter ownership of `DiscoveryWatermarkPort`; it no longer reads or
  writes watermark state.
- Preserved sitemap-only discovery, incremental filtering, raw HTML payloads,
  and retry-safe proposed-watermark calculation.
- Included the known HTTP status in a failed outcome so later persistence can
  apply the three-attempt terminal 404/410 rule.

## Tests

- Replaced adapter-side watermark-write assertions with batch assertions.
- Added immutable-model coverage and confirmed HTTP-status propagation.
- `uv run pytest -q`: 556 passed.
- `uv run ruff check src/huginn/elt/ingestion/models.py src/huginn/elt/ingestion/adapters/eu_startups.py tests/elt/ingestion/test_eu_startups.py`: passed.
- `git diff --check`: passed.

## Scope

Only Task 1 files are staged for the commit. Pre-existing uncommitted Bronze
web-scrape persistence work remains unmodified and unstaged.

## Follow-on

Task 2 can persist `DiscoveryBatch` atomically with the source watermark and
per-URL retry state. Task 3 can supply the persisted watermark to the adapter
and commit the returned batch through that dedicated repository.
