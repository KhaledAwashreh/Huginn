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
  `terminal_attempt_count`.
- A listing remains `retryable` after the first and second confirmed terminal
  response and becomes `terminal` on the third.
- Network failures and 5xx responses remain retryable regardless of total
  attempt count.
- Terminal failures stop pinning the committed watermark. Any remaining
  retryable failure pins it to one second before that listing's `lastmod`.

## Tests

Tests were written before the repository implementation. The first valid red
run failed collection with `ModuleNotFoundError` for the missing
`eu_startups_discovery_repository` module.

Unit coverage verifies:

- exact third-attempt terminalization for both 404 and 410;
- indefinite retryability for network and 5xx failures;
- mixed failure types count only confirmed 404/410 outcomes toward terminal
  status;
- watermark movement past terminal failures while remaining pinned by
  retryable failures;
- explicit rollback and resource cleanup when a transaction statement fails.

PostgreSQL integration coverage uses the existing `tests/conftest.py`
Testcontainers bootstrap and verifies:

- atomic successful Bronze-row and watermark commit;
- rollback leaves the prior Bronze rows and watermark unchanged;
- retry count and status persist across transactions;
- 404 and 410 terminalize exactly on their third persisted attempt.

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
