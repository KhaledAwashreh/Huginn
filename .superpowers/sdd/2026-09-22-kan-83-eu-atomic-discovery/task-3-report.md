# Task 3: Dedicated EU Discovery Runner

## Changes

- Added `EuStartupsDiscoveryRunner`, which reads the durable sitemap watermark
  and retryable listings, passes both to the discovery adapter, and commits the
  resulting `DiscoveryBatch` through the source-specific repository. The shared
  `IngestionService` remains unchanged.
- Extended the adapter's backwards-compatible `fetch()` signature to merge
  persisted retry URLs with sitemap candidates, including retries at or before
  the durable watermark.
- Closed the carried CodeRabbit stale-success race before enabling the runner:
  Bronze upserts only replace payloads when the incoming listing `lastmod` is
  not older, and retry deletion is likewise constrained by `lastmod`.
- Added unit and real PostgreSQL Testcontainers coverage for runner wiring,
  persistence rollback, retry replay, and the ordered newer-failure then stale-
  success regression.

## Commit

- `2f82ae1 feat: add EU discovery runner`

## Validation

- RED: runner tests initially failed collection with two
  `ModuleNotFoundError` errors before the runner existed.
- Focused suite:
  `rtk env UV_CACHE_DIR=/tmp/huginn-task3-uv-cache uv run pytest -q tests/elt/ingestion/test_eu_startups.py tests/elt/ingestion/test_eu_startups_discovery_runner.py tests/elt/ingestion/test_eu_startups_discovery_runner_integration.py tests/elt/bronze/test_eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository_integration.py`
  passed: `44 passed in 1.81s`. PostgreSQL Testcontainers tests executed with
  Docker access; none skipped.
- Dirty-worktree full suite: `579 passed in 20.99s`. This historical run
  included unrelated unstaged web-scrape tests and is not a clean
  committed-branch count.
- `rtk env UV_CACHE_DIR=/tmp/huginn-task3-uv-cache uv run ruff check .`:
  passed.
- `rtk env UV_CACHE_DIR=/tmp/huginn-task3-uv-cache uv run ruff format --check .`:
  `171 files already formatted`.
- `rtk env UV_CACHE_DIR=/tmp/huginn-task3-uv-cache uv run python -m compileall -q ...`:
  passed for all Task 3 modules and tests.
- `rtk git diff --check` and `rtk git diff --cached --check`: passed.

## Residual Risk

The existing operational prerequisite remains: deployments against a database
created before the EU discovery tables exist must apply the Bronze bootstrap
DDL, because this project has not introduced a migration framework yet.

## Scope

The pre-existing unstaged web-scrape repository/store work and its tests were
preserved and were not staged or committed.

## Fix Round 1/5: Production Entrypoint

### Finding Addressed

The production ingestion module now exposes an explicit
`eu-startups-discovery` command. It composes `EuStartupsDiscoveryAdapter`,
`PostgresEuStartupsDiscoveryRepository`, and `EuStartupsDiscoveryRunner` from
the configured database URL, then invokes only the dedicated runner. Calling
the module with no command preserves the existing HN/YC/OpenCorporates
`IngestionService.run_once()` behavior.

### Commit

- `67e8a3b fix: expose EU discovery command`

### RED Evidence

Before production wiring was added:

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix1-uv-cache uv run pytest -q tests/elt/ingestion/test_main.py
ERROR tests/elt/ingestion/test_main.py
ImportError: cannot import name 'build_eu_startups_discovery_runner'
1 error in 0.12s
```

### Validation

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix1-uv-cache uv run pytest -q tests/elt/ingestion/test_main.py tests/elt/ingestion/test_eu_startups_discovery_runner.py
........                                                                 [100%]
8 passed in 0.04s
```

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix1-uv-cache uv run pytest -q
581 passed in 19.39s
```

This was a dirty-worktree count that included unrelated unstaged web-scrape
tests, not a clean committed-branch result. The run had Docker access,
including PostgreSQL Testcontainers tests.

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix1-uv-cache uv run ruff check .
All checks passed!

$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix1-uv-cache uv run ruff format --check .
171 files already formatted

$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix1-uv-cache uv run python -m compileall -q src/huginn/elt/ingestion/__main__.py tests/elt/ingestion/test_main.py

$ rtk git diff --check
```

All commands exited successfully. The pre-existing dirty web-scrape files and
the unstaged `src/huginn/elt/bronze/ports.py` change remain untouched.

## Fix Round 2/5: Duplicate Sitemap Ordering

### Finding Assessment And Fix

The CodeRabbit finding was valid. The dictionary comprehension used
last-write-wins semantics, so a duplicate URL ordered newest-then-older kept
the older timestamp. The adapter now applies the existing watermark filter
first and retains the maximum parsed `lastmod` per URL. The subsequent durable
retry merge remains unchanged and continues to select the newer timestamp.
Malformed or missing `lastmod` entries remain filtered by the existing sitemap
parser before aggregation.

### Commit

- `0107bc1 fix: retain newest EU sitemap entry`

### RED Evidence

The parameterized regression passed for older-then-newer but failed for
newest-then-older before the production change:

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix2-uv-cache uv run pytest -q tests/elt/ingestion/test_eu_startups.py -k duplicate_url
F.                                                                       [100%]
1 failed, 1 passed, 23 deselected in 0.11s
```

The failure observed `2026-09-05T00:00:00+00:00` instead of the expected
`2026-09-10T00:00:00+00:00`.

### Validation

```text
$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix2-uv-cache uv run pytest -q tests/elt/ingestion/test_eu_startups.py
25 passed in 0.13s

$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix2-uv-cache uv run pytest -q
583 passed in 19.17s

$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix2-uv-cache uv run ruff check .
All checks passed!

$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix2-uv-cache uv run ruff format --check .
171 files already formatted

$ rtk env UV_CACHE_DIR=/tmp/huginn-task3-fix2-uv-cache uv run python -m compileall -q src/huginn/elt/ingestion/adapters/eu_startups.py tests/elt/ingestion/test_eu_startups.py

$ rtk git diff --check
```

All commands exited successfully. The `583` result was a dirty-worktree count
that included unrelated unstaged web-scrape tests, not a clean committed-branch
result. The run had Docker access, so PostgreSQL Testcontainers coverage
executed. Pre-existing dirty web-scrape files and the unstaged
`src/huginn/elt/bronze/ports.py` change remain untouched.

## Final Review Fix Wave

### Findings Addressed

1. A delayed failure whose `lastmod` is older than an already persisted
   EU-Startups Bronze record now becomes an atomic no-op. Under the existing
   transaction advisory lock, the repository compares the failure with the
   durable successful record for that URL before retry upsert or checkpoint
   work. Network and 503 stale failures cannot create an endlessly replayed
   retry row or touch the checkpoint.
2. `db/schema/kan-83-eu-startups-discovery.sql` is the one idempotent,
   additive deployment step for a pre-KAN-83 database. Fresh bootstrap, CI,
   and Testcontainers apply the same file after `bronze.sql`, avoiding a
   duplicate DDL source. It adds only the KAN-83 state/retry tables and their
   supporting indexes; it is not general migration tooling.
3. This report now labels the earlier `579`, `581`, and `583` totals as dirty
   worktree results rather than clean committed-branch evidence.

### Commits And Clean Evidence

- `ba6b317 fix: harden EU discovery persistence`
- Reviewer clean archive at `0107bc1`: focused `53 passed`; full
  `571 passed`.
- Final-review clean detached archive at `ba6b317`: focused `56 passed in
  1.83s`; full `574 passed in 22.36s`. Docker-backed PostgreSQL
  Testcontainers tests executed, and `git status --short` plus
  `git diff --check` were empty in that archive.

### Validation

- RED: the two stale-failure Testcontainers cases inserted retry rows under
  the prior repository; the additive-upgrade case failed because the SQL file
  did not exist.
- GREEN: new focused cases `3 passed`; complete EU-focused suite `56 passed`.
- Clean archive: `ruff check .`, `ruff format --check .`, and
  `python -m compileall -q src tests` passed; `167 files already formatted`.

### Residual Risk

The KAN-83 SQL is intentionally limited to a pre-KAN-83 Bronze schema. Future
schema evolution still needs the separately deferred KAN-49 migration
framework decision; this one-off additive file must not be treated as a
general migration system.

## Human-Authorized Extra Final-Review Fix Wave

### Resolution

1. The destructive pre-KAN-83 upgrade test now creates a UUID-named database
   through the server's `postgres` maintenance database, runs all DDL and test
   data against that temporary DSN, and drops it with `WITH (FORCE)` in the
   context manager's `finally` block. It verifies the configured database's
   name and relevant Bronze relation OIDs remain unchanged. A failed create
   attempts cleanup only when the generated database exists. The helper rejects
   psql meta-commands because it executes the two pre-KAN-83 SQL files through
   psycopg, not psql.
2. Durable retry rows no longer choose the committed checkpoint. The repository
   advances from the current batch's processed/proposed outcomes, while the
   runner continues to replay retry rows at or before the durable watermark.
   PostgreSQL coverage proves a later successful record advances the checkpoint
   without deleting its older retry row. Existing stale-outcome, terminal,
   newer-cycle, rollback, and advisory-lock coverage remains green.
3. `docs/management-foundation.md` now correctly calls the verified bootstrap
   command seven-file. The command lists seven `-f` schema arguments, matching
   `tests/conftest.py`.
4. The successful-listing `lastmod` query now has the literal
   `source = 'eu_startups'` predicate and receives only `failure.url`.

### RED Evidence

Before the production changes:

```text
rtk env UV_CACHE_DIR=/tmp/huginn-kan83-extra-red-uv-cache uv run pytest -q tests/elt/bronze/test_eu_startups_discovery_repository.py tests/elt/bronze/test_eu_startups_discovery_repository_integration.py::test_kan_83_additive_upgrade_isolated_from_configured_database_and_cleans_up tests/elt/ingestion/test_eu_startups_discovery_runner.py
```

Result: `2 failed, 4 passed, 1 skipped in 0.22s`.

1. `committed_watermark()` still required retryable lastmods and the new
   independent-checkpoint regression raised `TypeError`.
2. `_READ_SUCCESSFUL_LISTING_LASTMOD_SQL` still used `source = %s`.
3. The integration case skipped because this sandbox could not access Docker.
   It was later run against Testcontainers and did not skip.

### Validation

1. Focused unit and adapter suite: `31 passed in 0.17s`.
2. Final focused EU discovery suite with real PostgreSQL Testcontainers:
   `52 passed in 2.68s`.
3. Final repository and runner PostgreSQL suite after strengthening the
   maintenance-database isolation helper: `21 passed in 2.76s`.
4. Scoped `ruff check` passed. Scoped `ruff format --check` reported six files
   already formatted. `python -m compileall -q src tests` and `git diff --check`
   passed.
5. Isolated clean-worktree validation at committed evidence revision `088c1df`:
   `577 passed in 17.23s` with external database configuration unset and
   Testcontainers running PostgreSQL. The worktree was clean before and after
   the run. Whole-repository `ruff check`, `ruff format --check` (`168 files
   already formatted`), `python -m compileall -q src tests`, and
   `git diff --check` passed there.
6. No live HTTP requests were made. Adapter coverage uses fixtures and the
   database suites use Testcontainers.

### Residual Risk

The isolated upgrade test intentionally requires access to the server's
`postgres` maintenance database and `CREATE DATABASE`. Normal Testcontainers
runs provide both and executed the test. A separately supplied database role
without those permissions cannot run this destructive-schema test safely and
will skip it rather than mutate the configured database.

## Focused Review Of 23db99e

### Resolution

1. The temporary pre-KAN-83 database helper now enters cleanup protection
   immediately after a successful `CREATE DATABASE`. State capture, DSN
   construction, schema setup, assertions, and the test body all run under the
   same `finally` cleanup. A regression forces configured-state capture to fail
   after creation and confirms the generated database is absent afterward.
2. `committed_watermark()` now derives the checkpoint from all effective
   records, active failures, and the adapter proposal. When an older failure is
   filtered as stale, a later successful record in the same transaction
   advances the checkpoint while leaving Bronze and retry state correct.

### RED Evidence

```text
rtk env UV_CACHE_DIR=/tmp/huginn-kan83-review2-red-uv-cache uv run pytest -q tests/elt/bronze/test_eu_startups_discovery_repository.py::test_later_success_advances_watermark_after_stale_failure_is_filtered tests/elt/bronze/test_eu_startups_discovery_repository_integration.py::test_temporary_database_is_dropped_when_post_create_setup_fails tests/elt/bronze/test_eu_startups_discovery_repository_integration.py::test_stale_failure_and_later_success_commit_record_without_retry_and_advance
```

Result: `3 failed in 0.78s`. The failures demonstrated the old pinned
watermark in unit and PostgreSQL coverage and the leaked temporary database
after post-create state capture failed.

### Validation

1. The three new regressions passed with PostgreSQL Testcontainers:
   `3 passed in 0.45s`.
2. Complete repository unit and PostgreSQL integration coverage:
   `26 passed in 3.01s`.
3. Complete EU discovery adapter, runner, repository, and PostgreSQL suite:
   `55 passed in 3.18s`.
4. Scoped Ruff check and format check passed (`3 files already formatted`).
   `python -m compileall -q` for the changed source and tests and
   `git diff --check` also passed.
5. No live HTTP requests were made. Adapter coverage uses fixtures and the
   database suites use Testcontainers.
6. Detached clean-worktree validation at code-evidence revision `af98335`:
   `580 passed in 21.27s` with `HUGINN_DATABASE_URL` unset and PostgreSQL
   Testcontainers running. Whole-repository Ruff check, Ruff format check
   (`168 files already formatted`), `python -m compileall -q src tests`,
   `git diff --check`, and clean status checks passed.

### Residual Risk

The isolated upgrade test still requires access to the server's `postgres`
maintenance database and `CREATE DATABASE`. Normal Testcontainers runs provide
both. A separately supplied role without those permissions skips the isolated
schema test rather than mutating the configured database.
