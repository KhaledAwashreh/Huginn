# Task 2 Report: Transactional Persistence

## Outcome

Implemented the source-specific PostgreSQL persistence boundary for
EU-Startups discovery.

- Added `bronze.eu_startups_discovery_state` for the durable sitemap
  watermark.
- Added `bronze.eu_startups_listing_retry` for per-URL attempt count,
  confirmed terminal-response count, last HTTP status, and retry status.
- Added `EuStartupsDiscoveryRepositoryPort` without changing shared ingestion
  contracts.
- Added `PostgresEuStartupsDiscoveryRepository.read_watermark()` and
  `commit_batch()`.
- `commit_batch()` writes or touches successful Bronze rows, clears recovered
  listing failures, updates failed-listing retry state, and advances the
  watermark in one PostgreSQL transaction.
- Watermark writes use `GREATEST` to prevent checkpoint regression.
- Retry increments use one atomic PostgreSQL upsert, so concurrent commits do
  not lose an attempt.

## Retry Policy

- Every failed listing increments `attempt_count`.
- Only confirmed HTTP 404 or 410 outcomes increment
  `terminal_attempt_count`, which is retained as failure telemetry.
- A listing becomes `terminal` when the current outcome is a confirmed 404 or
  410 and the resulting total `attempt_count` is at least three.
- A current network failure or 5xx response remains retryable regardless of
  total attempt count, including after an earlier terminal outcome.
- Terminal failures stop pinning the committed watermark. Any remaining
  retryable failure pins it to one second before that listing's `lastmod`.

## Tests

Tests were written before the repository implementation. The first valid red
run failed collection with `ModuleNotFoundError` for the missing
`eu_startups_discovery_repository` module.

Unit coverage verifies:

- watermark movement past terminal failures while remaining pinned by
  retryable failures;
- explicit rollback and resource cleanup when a transaction statement fails.

PostgreSQL integration coverage uses the existing `tests/conftest.py`
Testcontainers bootstrap and verifies:

- atomic successful Bronze-row and watermark commit;
- rollback leaves the prior Bronze rows and watermark unchanged;
- retry count and status persist across transactions;
- 404 and 410 terminalize exactly on their third persisted attempt;
- mixed outcomes use total attempt count and current response type for status.

The integration tests actually executed against PostgreSQL; none skipped.

- Task 2 focused suite: `14 passed`.
- Full suite: `571 passed`.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed.
- `git diff --check`: passed.

## Scope

- Sitemap-only discovery is unchanged.
- The adapter, shared `IngestionService`, HN, YC, and OpenCorporates were not
  changed.
- Task 3's discovery runner was not implemented.
- Pre-existing uncommitted web-scrape store/repository work and its tests were
  preserved and remain unstaged.

## Review

The final review found and fixed a possible lost retry increment when two
transactions first failed the same URL concurrently. Retry state now advances
through a single `INSERT ... ON CONFLICT DO UPDATE ... RETURNING` statement.

## Concern

`db/schema/bronze.sql` is the project's fresh-database bootstrap. The project
does not yet have a migration framework, so applying these tables to an
existing database remains an operational follow-up outside Task 2.

## Fix Round 1/5: Retry Terminalization Policy

### Findings Addressed

1. Changed production terminalization to require both a current confirmed
   404/410 and a resulting total `attempt_count >= 3`. The mixed sequence
   `503 -> 404 -> 410` now terminalizes on its third failed attempt, while a
   subsequent 503 is retryable.
2. Removed the unused `ListingRetryState` and `advance_retry_state()` Python
   policy duplicate. Retry-policy assertions now execute `commit_batch()`
   against PostgreSQL.

### Red Evidence

The new mixed-status Testcontainers regression failed before the production
change at attempt 3:

- expected `(3, 2, 410, "terminal")`;
- observed `(3, 2, 410, "retryable")`;
- run result: `1 failed, 5 passed`.

### Verification

- Focused repository unit and PostgreSQL integration suite: `9 passed`,
  `0 skipped`.
- Both all-404 and all-410 third-attempt integration cases still pass.
- Mixed `503 -> 404 -> 410 -> 503` integration case proves statuses
  `retryable -> retryable -> terminal -> retryable`.
- Focused `ruff check`: passed.
- Focused `ruff format --check`: passed (`3 files already formatted`).
- `git diff --check`: passed.

### Scope

Only the source-specific repository, its focused unit/integration tests, and
this report changed. The adapter, runner, shared ingestion service, other
sources, and pre-existing uncommitted web-scrape work remain untouched.
