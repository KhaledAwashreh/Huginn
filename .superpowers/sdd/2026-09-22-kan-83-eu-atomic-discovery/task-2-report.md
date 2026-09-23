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
- Before terminalization, a current network failure or 5xx response remains
  retryable regardless of total attempt count.
- Terminal status is sticky across later failures for the same listing
  `lastmod` because the watermark may already have advanced. A strictly newer
  `lastmod` starts a fresh retry cycle, and a successful listing write clears
  the retry row.
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
through a single `INSERT ... ON CONFLICT DO UPDATE` statement.

## Concern

`db/schema/bronze.sql` is the project's fresh-database bootstrap. Per the
round 2 migration ruling, no migration framework is added. Applying the
bootstrap DDL to an existing database is an operational prerequisite before
Task 3 is enabled.

## Fix Round 1/5: Retry Terminalization Policy

### Findings Addressed

1. Changed production terminalization to require both a current confirmed
   404/410 and a resulting total `attempt_count >= 3`. The mixed sequence
   `503 -> 404 -> 410` now terminalizes on its third failed attempt.
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
- Mixed `503 -> 404 -> 410` integration case proves statuses
  `retryable -> retryable -> terminal`. Round 2 supersedes the earlier
  post-terminal transition by making terminal state sticky.
- Focused `ruff check`: passed.
- Focused `ruff format --check`: passed (`3 files already formatted`).
- `git diff --check`: passed.

### Scope

Only the source-specific repository, its focused unit/integration tests, and
this report changed. The adapter, runner, shared ingestion service, other
sources, and pre-existing uncommitted web-scrape work remain untouched.

## Fix Round 2/5: Persisted Retry Pins and Sticky Terminal State

### Findings Addressed

1. `commit_batch()` now reads every persisted retryable listing after applying
   current successes and failures, then pins the checkpoint one second before
   the earliest retryable `lastmod`. A later success-only batch cannot advance
   beyond an older unresolved listing.
2. Added `list_retryable_listings()` to the repository port and PostgreSQL
   repository. It returns durable URL, `lastmod`, and last-status state in
   deterministic `lastmod, url` order for Task 3's future replay path. No
   runner was added.
3. Terminal retry rows remain terminal across later network/5xx failures for
   the same listing version. Round 3 adds the newer-version reset rule. The
   existing successful-listing path still deletes the matching retry row.
4. Preserved the existing schema DDL and documented bootstrap application as
   an operational prerequisite; no migration framework was added.

### Red Evidence

The two new PostgreSQL regressions failed before implementation:

- persisted retry listing: `AttributeError` because
  `list_retryable_listings()` did not exist;
- sticky terminal listing: expected `(4, 503, "terminal")`, observed
  `(4, 503, "retryable")`;
- run result: `2 failed, 6 passed in 0.52s`.

### Verification Commands And Outputs

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task2-uv-cache uv run pytest -q tests/elt/bronze/test_eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository_integration.py
...........                                                              [100%]
11 passed in 0.52s
```

All 11 tests executed: 3 unit and 8 PostgreSQL Testcontainers cases. Zero
tests skipped.

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task2-uv-cache uv run ruff check src/huginn/elt/bronze/ports.py src/huginn/elt/bronze/repositories/eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository_integration.py
All checks passed!
```

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task2-uv-cache uv run ruff format --check src/huginn/elt/bronze/ports.py src/huginn/elt/bronze/repositories/eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository_integration.py
4 files already formatted
```

```text
$ rtk git diff --check
```

`git diff --check` produced no output and exited 0.

### Scope

Only the EU discovery repository interface/implementation, focused tests, and
this report changed. Schema DDL, adapters, the shared ingestion service, other
sources, and Task 3's runner remain unchanged. Pre-existing uncommitted
web-scrape work remains preserved and unstaged.

## Fix Round 3/5: Listing-Version Retry Reset

### Finding Addressed

Terminal state is now sticky only while failures carry the same listing
`lastmod`. When a URL fails with a strictly newer `lastmod`, the atomic retry
upsert starts a new cycle:

- `attempt_count = 1`;
- `terminal_attempt_count = 1` for a current 404/410, otherwise `0`;
- `status = retryable`;
- the new `lastmod` is persisted and exposed by `list_retryable_listings()`;
- the checkpoint remains one second before the newer unresolved listing.

Equal or older `lastmod` failures retain the existing sticky-terminal and
attempt-accumulation behavior. Successful listing writes still clear retry
state.

### Red Evidence

The new PostgreSQL regression first terminalized an old listing version with
three 404s, then submitted a newer version with a 503. Before the fix it
observed `(attempt_count=4, terminal_attempt_count=3, status="terminal")`
instead of `(1, 0, "retryable")`.

- run result: `1 failed, 8 passed in 0.84s`.

### Verification Commands And Outputs

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task2-uv-cache uv run pytest -q tests/elt/bronze/test_eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository_integration.py
............                                                             [100%]
12 passed in 0.75s
```

All 12 tests executed: 3 unit and 9 PostgreSQL Testcontainers cases. Zero
tests skipped.

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task2-uv-cache uv run ruff check src/huginn/elt/bronze/repositories/eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository_integration.py
All checks passed!
```

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task2-uv-cache uv run ruff format --check src/huginn/elt/bronze/repositories/eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository_integration.py
3 files already formatted
```

```text
$ rtk git diff --check
```

`git diff --check` produced no output and exited 0.

### Scope

Only the EU discovery retry upsert, its PostgreSQL regression, and this report
changed. Schema DDL, ports, adapters, the shared ingestion service, other
sources, and Task 3 remain unchanged. Pre-existing uncommitted web-scrape work
remains preserved and unstaged.
