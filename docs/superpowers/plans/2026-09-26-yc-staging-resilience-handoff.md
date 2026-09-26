# Handoff: YC staging loader resilience (E0)

Status: **code complete, all gates green, awaiting final sign-off review.**
Branch `refactor/ingestion-connectors-di`, HEAD `fcc00e6`, nothing committed,
nothing pushed. Work is uncommitted on 4 files.

## Why this artifact exists

A different model picks this up. Read this before touching the code. The
short version: the change is correct now, but two of the defects found during
review were only caught by *measuring against the live database*, not by
reasoning about the code. Do not trust reasoning alone on this file.

## Current state

```
687 passed
ruff check: All checks passed
ruff format: 176 files already formatted
57 tests in tests/elt/silver/test_yc_staging.py, 0 duplicate names
live integration: 11 passed (tests/elt/silver/test_yc_staging_integration.py)
```

Modified, uncommitted:

| File | Change |
|---|---|
| `src/huginn/elt/silver/yc_staging.py` | The change itself |
| `tests/elt/silver/test_yc_staging.py` | +442 lines, 16 new tests |
| `src/huginn/elt/silver/models.py` | 3 `description` hints widened to `str \| None` |
| `docs/entities.md` | +6 lines documenting the skip buckets |

## What the change does

`YcStagingLoader.load` shares one `with self._repository:` scope, so an
exception escaping mid-batch rolls back every row already written. Bronze is
immutable and re-read whole each run, so that is not one lost run, it is a
permanent outage for the table. The change stops one malformed Algolia payload
from causing that.

1. A payload that cannot be parsed is skipped, logged at WARNING with its YC
   `id` and the exception type, counted, and the loop continues.
2. The catch is narrow, per `BEST_PRACTICES.md:197-200`, not bare `Exception`.
3. `upsert` is deliberately OUTSIDE the parse catch, because a SQL error
   aborts a Postgres transaction and catching it would hide a real failure
   without recovering the batch.
4. Writes stay all-or-nothing. No savepoint, no per-row commit.
5. Five summary counts, which must always sum to the bronze rows read:
   `written`, `not_a_prospect`, `no_launch_date`, `unclassified`, `rejected`.
6. `_skip_reason` is the only place the skip conditions are written. A reason
   the summary has no bucket for is warned, not silently filed under a
   business rule.

## The five defects review found, and what fixed them

Ordered by how close each came to real damage. The first two are the reason
this file needs care.

### 1. `OSError` hole, would have rolled back the batch (CLOSED)

The catch named `OverflowError` for out-of-range timestamps. Measured on this
platform:

```
1e12    -> ValueError: year must be in 1..9999      (not named in comment)
1e18    -> OSError: [Errno 75] Value too large      (ESCAPED the catch)
10**20  -> OverflowError: timestamp out of range
```

`OSError` and `OverflowError` are both **not** `ValueError` subclasses, so a
plausible-looking wrong timestamp escaped into the shared transaction and
rolled the whole batch back, which is the exact outage this change exists to
prevent. Fixed by adding `OSError` and reordering the comment to the measured
order. Tests cover all three bands.

### 2. `description` regression, blanked 210 live rows (CLOSED, self-inflicted)

I changed description handling to distinguish NULL from `""`. I tested for
`None`:

```python
description = payload.get("long_description")
if description is None:
    description = payload.get("one_liner")
```

`""` is not `None`, so an empty `long_description` beat a populated
`one_liner`. Measured on the live dev DB: 386 rows have an empty
`long_description`, 344 of those have a populated `one_liner`, 227 are
promotable, and **210 currently staged rows would silently lose their
description text**, flowing on to `silver.resolved_signals.description` and
`gold.company_signal.description`. Meanwhile 0 live rows lack both keys, so the
NULL branch the change was written for never fires. The side effect fired on
210 rows and the intent fired on none.

Fixed with `or` on both sides, which yields NULL when neither key is present,
`""` when both are empty, and the fallback otherwise. Regression test uses the
live shape (empty `long_description`, populated `one_liner`).

**Lesson: this was caught only by querying the live database. Reasoning about
`None` versus `""` did not catch it, and neither did reading the diff.**

### 3. Duplicate skip conditions, silent row loss (CLOSED, self-inflicted)

`_skip_reason` was introduced to be the single source of truth, but the
conditions were written in both `_skip_reason` and `parse_yc_sting`, and
`load` had an `else` fallthrough filing anything unrecognised under "not a
prospect". Adding a third reason to the parser alone dropped the row with no
warning, reported as a deliberate business rule, and **all tests still
passed**. Fixed by having `parse_yc_listing` and `load` both read
`_skip_reason`, plus a dedicated `unclassified` bucket that warns. The exact
exploit is now a test.

### 4. Mislabelled bucket, an operator-facing lie (CLOSED, self-inflicted)

The summary reported a missing `launched_at` under "skipped as
acquired/inactive". An operator would read a source-data problem as a
deliberate business-rule exclusion, which is the precise thing the separate
buckets exist to prevent. Fixed by splitting the buckets. Note the ordering
that caused it: status is checked first, so a row that is both acquired and
undated is counted once as not-a-prospect, and its missing date goes
unreported. That is now documented and pinned by a test.

### 5. Unreachable warning, dead in the real pipeline (CLOSED)

`parse_yc_listing` logged a WARNING for undated rows, but `load` consults
`_skip_reason` before calling the parser, so that warning **never fired on the
pipeline's own path**. A test calling the parser directly passed, giving false
confidence. Fixed by moving the warning into `load`, where ADR-0005 wants
stage-boundary logging anyway. The test now goes through `load`.

Also fixed along the way:

- Two **fabricated history claims** in test docstrings ("an earlier version
  counted..."). Git history shows the pre-change parser had no `launched_at`
  branch at all, so it was never counted anywhere. This repo has a commit
  specifically for correcting claims of that kind. Removed.
- A **duplicate test name** that shadowed another, so one test silently never
  ran while pytest reported all-passed. Ruff caught it. **Check
  `def test_` count equals `--collect-only` count on this file after any
  edit.**
- `BEST_PRACTICES.md` forbids bare `except Exception`, so the narrow-catch
  rationale now states the accepted cost plainly: the tuple cannot distinguish
  bad source data from a bug, because those types are what both raise. A
  defect of a covered class shows up as a rising rejected count, not a
  traceback. Nothing is swallowed; every decline is counted.

## Deliberate decisions, do not "fix" these

- **The narrow catch cannot tell bad data from a bug.** Documented and
  accepted. The per-row WARNING is what makes it diagnosable.
- **`not_a_prospect` is count-only, no per-row warning.** 1,903 of 6,252 live
  rows are excluded by design, so a warning each would bury the summary.
  Pinned by a test.
- **`logger.warning`, not `logger.exception`, for a declined row.** A decline
  is an expected, counted outcome, not a fault. ADR-0005 deviation is cited
  and justified in the docstring.
- **`_skip_reason` is status-first.** Acquired-plus-undated counts once, as
  not-a-prospect. Harmless only because `launched_at` is non-null on every
  live row today. If that changes, revisit.
- **`_listing_field` uses `isinstance`, not a broad `except`.** A bronze
  payload is JSONB and therefore always a real dict, and a dict's `.get`
  cannot raise, so the log-building path is already safe. A broad `except`
  here would break the repo rule to defend an unreachable case.
- **The `upsert` guard is a parser-shape guard, not a type guard.** A field
  that parses but carries the wrong type, a `dict` where a string belongs,
  reaches Postgres and is rejected there, rolling the batch back the same
  way. No live row does this. It is source-drift exposure, not a current
  fault, and it is pre-existing rather than introduced here.
- **Left alone as stale, all pre-existing:** the repo says 6,252 YC bronze
  rows, the live dev DB has 6,258. Also `team_size == 0` is 134 not 133, and
  `industries > 1` is 4,906 not 4,899. `test_yc_staging.py` also carries a
  `6204` from the KAN-34 plan doc. Every *new* claim added in this change is
  dated "as of 2026-09" and was checked against the DB. The undated ones
  beside them are stale. Not churned, to keep the diff scoped.

## Verification method, if you change this file

Do not trust the tests alone. Both worst defects survived a full read of the
diff. Use all three:

1. Full gates: `./.venv/bin/python -m pytest -q`, `./.venv/bin/ruff check .`,
   `./.venv/bin/ruff format --check .`
2. Mutation checks. Every guard below has a mutation that must fail. The
   pattern is: back up the file to `/tmp`, apply one change, run the test
   file, confirm it fails, restore. Confirmed killed: no catch at all; catch
   broadened to `Exception`; each of the five counters hardcoded to 0; log
   args swapped; bronze total dropped; rejected id dropped from the warning;
   rejection logged at ERROR; launch-date bucket folded into not-a-prospect;
   unknown reason silently bucketed; `_skip_reason` conditions removed;
   per-row scope instead of one shared scope; undated warning text changed;
   `upsert` moved inside the `try`; `description` None-test; `description`
   with an `or ""` fallback; each of `ValueError`, `OSError`,
   `OverflowError` dropped from the tuple; a per-row warning added to the
   not-a-prospect bucket.
3. Live database checks for any claim about data shape or counts. The
   `description` and `OSError` defects were both invisible to code reading and
   obvious against the DB.

## Remaining work, not part of E0

E0 is the first of five planned efforts. The rest is unwired, and the tree
must stay green between efforts.

**What is settled and what is not.** E1's shape is settled and the API
surface below is verified against the code. E2's policy is **not** decided and
must not be invented. E3 and E4 are mechanical once E1 lands. Each effort gets
its own build, validator, and reviewer pass before the next starts, per the
method section at the end.

### E1, the actual goal: wire Silver and Gold into a runnable pipeline

Nothing currently calls the Silver or Gold writers. This is the main
deliverable and it is untouched. A new `src/huginn/elt/__main__.py`, run as
`python -m huginn.elt`, running seven stages in order.
`python -m huginn.elt.ingestion` must keep working for ingestion-only.

| # | `job_runs.source` label | Call | Writes | Entry point |
|---|---|---|---|---|
| 1 | `ingestion` | `IngestionService.run_once()` | `bronze.api_ingest`, plus its own per-source rows | `ingestion/service.py:40` |
| 2 | `silver.hn_staging` | `HnStagingLoader(...).load()` | `silver.hn_postings` | `silver/hn_staging.py:131` |
| 3 | `silver.yc_staging` | `YcStagingLoader(...).load()` | `silver.yc_listings` | `silver/yc_staging.py:181` |
| 4 | `silver.signal_resolution` | `SignalResolver(...).resolve_all()` | `silver.resolved_signals` | `silver/signal_resolution.py:119` |
| 5 | `silver.manual_review` | `ManualReviewQueuer(...).queue_unmatched()` | `silver.manual_review_queue` | `silver/manual_review.py:33` |
| 6 | `gold.company` | `CompanyWriter(...).write_all()` | `gold.company`, and `gold.company_history` on update only | `gold/company.py:160` |
| 7 | `gold.company_signal` | `CompanySignalWriter(...).write_all()` | `gold.company_signal` | `gold/company_signal.py:28` |

Concrete repositories, all taking a `database_url`:
`PostgresHnStagingRepository`, `PostgresYcStagingRepository`,
`PostgresSignalResolutionRepository`, `PostgresManualReviewRepository`
(all in `src/huginn/elt/silver/repositories/`), `PostgresCompanyRepository`
and `PostgresCompanySignalRepository` (in `src/huginn/elt/gold/repositories/`).

**Why the order is load-bearing, verified not assumed:**

- Stage 7's read query joins `silver.resolved_signals` to `gold.company` on
  domain, so stage 6 must have written rows first or stage 7 matches nothing.
- Stage 4 reads `read_hn_postings() + read_yc_listings()`, so both staging
  stages must precede it.
- Stage 5 reads only `resolved_signals`, so it is a sibling of Gold, not a
  prerequisite. It can move after 4.
- `gold.company_history` being empty is expected, not a bug: `CompanyWriter`
  writes history only when a company already exists and changed
  (`gold/company.py:107-114`).

**Design constraints:**

- Internal shape mirrors `src/huginn/elt/ingestion/__main__.py` so it reads
  like the existing entry point: a frozen `Stage` dataclass (`name`, `run`),
  a `build_stages(config)`, a `run_stages(...)`, and `main()` owning logging
  setup and the exit code.
- `build_stages` is DB-free and therefore unit-testable: every repository
  connects in `__enter__`, not `__init__` (`silver/repositories/postgres_repository.py:21`).
- Per-stage elapsed time is logged. The user chose **ship resolution
  unchanged and measure the real cost**; do not add incremental resolution or
  bounded concurrency without asking. Resolution re-probes every domain every
  run via `check_domain_reachable` (`silver/resolution.py:105`), 5.0s default
  timeout, HEAD then GET, one retry, currently sequential, roughly 4,434 calls
  per run. The first real run will likely take 30 to 60+ minutes; that is
  expected, and the elapsed logging is what turns it into a number instead of
  a guess.
- Zero rows from a stage is success, not failure. `queue_unmatched()`
  legitimately returns 0 on a no-change rerun.

**HN carries the same hazard E0 just fixed, and is NOT in E0's scope.**
`silver/hn_staging.py:103-110` indexes `payload["id"]` and `payload["time"]`
directly and calls `datetime.fromtimestamp` unguarded, so an HN freeform
comment has the same all-or-nothing batch-wedge potential, including the
`OSError` band. E0 deliberately did not touch it. Decide explicitly whether
to extend the E0 fix to HN in E1 or file it separately, and say which.

**Tests to write (all DB-free):** stage order and exact labels; a stage that
raises means later stages never run, the failure is returned, and a FAILED
`job_run` carries the error text; a stage returning 0 is SUCCEEDED;
`main()` exits 1 on stage failure and on missing config, matching ingestion;
elapsed time is logged per stage. Mutation checks: removing the abort must let
a later stage run and fail a test, and dropping the FAILED write must fail a
test.

**Destructive step needing explicit user approval:** recreating
`huginn-verify-pg` empty for one true end-to-end run. Not required to wire and
test, since the testcontainer harness covers that. See the provenance warning
below.

### E2, stage-failure isolation

The originally planned policy was abort-on-first-failure, justified by "Gold
depends on Silver freshness, so continuing would write Gold from stale Silver."
**That policy has a known bad case and the user has not ruled on it:** stage 4
makes thousands of network calls, so one DNS or HTTP blip aborts the run and
leaves Gold stale and unreadable indefinitely, with no degraded-but-valid
output. The candidate options, none approved:

1. Ship abort-on-first-failure as planned and accept the blip behaviour.
2. Classify stages: abort on a database or logic failure, continue past a
   network-only failure and let Gold run on the previous resolution.
3. Something else the user prefers.

Do not pick one silently. This is a product decision about whether a partial
run is better than no run, and the trade-off is not symmetric.

If a reachable-signal lookup is needed to tell a network failure from a logic
failure, the domain repository has to grow a read for it, which is a real API
change, not a one-liner. Budget for that.

### E3, docs

- `README.md`: the status line claiming no live run has driven Silver and
  Gold, the run command at `README.md:25`, and the cron example at
  `README.md:33`. The cron line matters operationally: if it still invokes
  `python -m huginn.elt.ingestion` after E1 lands, ingestion double-runs until
  someone edits it.
- `docs/architecture.md`: the pipeline entry point alongside section 5's
  ingestion entry point.
- `src/huginn/ops/job_runs.py` docstring and `db/schema/ops.sql` comment:
  `source` would identify a pipeline unit, ingestion source or stage, not
  only an ingestion source. No migration needed, the column already holds a
  short string.
- Re-check `docs/entities.md` for the E0 addition still reading correctly once
  E1 exists.

### E4, ADR-0014

`adr/0014-pipeline-entry-point-and-stage-failure-policy.md`, MADR format per
`CLAUDE.md` design standard 7. Covers three separable decisions: the single
entry point, the stage order and its dependency argument, and the
stage-failure policy. If E2 changes the failure policy, the ADR records the
decided policy, not the planned one. Numbering must not collide with existing
ADRs; check `adr/` before writing.

### Open questions the next model must not answer alone

- **`job_runs.source` semantic stretch.** Documented as an ingestion source;
  stage labels stretch it. Correcting the docstring and `ops.sql` comment is
  clearly in scope. Whether this needs its own ADR is not decided.
- **EU-Startups cannot be wired.** `EuStartupsStagingRepositoryPort` has no
  Postgres implementation. The user says merging
  `integration/kan-83-eu-persistence` resolves this, but that branch was not
  merged and its persistence commits were never reviewed. Verify after merge.
- **The verification database has mixed provenance.** `huginn-verify-pg` has
  populated Bronze, Silver and Gold tables, but no committed Silver or Gold
  runner has ever existed, and `ops.job_runs` holds only ingestion rows. The
  exact writer is unknown. Some of it is almost certainly test or fixture
  data loaded before the isolation guards existed. **Do not delete or recreate
  it without explicit authorisation**; it is the only place the 210-row and
  386-row figures above can be re-verified.
- **OpenCorporates token.** A full pipeline run includes the existing
  ingestion service, which needs `HUGINN_OPENCORPORATES_API_TOKEN`. The user
  deferred OpenCorporates work, so confirm how the full command should behave
  without it.
- **Check the crontab** before wiring, so ingestion is not double-run.

## Repo rules that shaped this

- `BEST_PRACTICES.md:197-200` forbids broad `except Exception`. Cite it, do
  not restate it.
- `BEST_PRACTICES.md` section 3: docstrings cite the architecture document or
  an ADR by name. There is no maximum length, so length alone is not a
  defect; restatement and falsity are.
- No em dashes in added lines.
- Ruff for lint and format. Pyright is deferred: do not add it, and note that
  the `description: str | None` widening is therefore not machine-checked
  today.
- No commit and no push without the user's explicit say-so. No Claude or
  Anthropic attribution in commits.

## Method that worked, keep using it

Each effort ran a build, then an independent validator with an explicit
acceptance list, then a fresh code reviewer, with mutation checks and live
database verification behind both. The validator found the mislabelled bucket
and the duplicate conditions; the reviewer found the `OSError` hole and the
210-row `description` regression. Neither would have been caught by the author.
Gating each effort before starting the next is what kept this from compounding.

The single most valuable habit: **measure against the live database before
believing any claim about data shape or counts**, including claims in comments
that predate this change.
