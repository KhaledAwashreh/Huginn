# KAN-28: IngestionService Per-Source Error Isolation and job_runs Wiring

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `IngestionService.run_once()` isolate one source's failure from
the others (a raising `fetch()` or `raw_store.write()` must not abort the
loop), and wire each source's outcome through `huginn.ops.job_runs`
(`start_job_run`/`finish_job_run`) into the existing `JobRunWriterPort`, with
logging at the run and per-source boundaries per ADR-0005.

**Architecture:** `IngestionService` gains a third constructor dependency,
`job_run_writer: JobRunWriterPort`. `run_once()` wraps each source's
`start_job_run` → `fetch()` → `raw_store.write()` → `finish_job_run` sequence
in one `try`/`except Exception`, writes the resulting terminal `JobRun`
through `job_run_writer.write(...)`, logs success or failure at that
boundary, and continues to the next source either way. No new dependency: the
existing `huginn.ops.job_runs` module (KAN-27, already merged) and stdlib
`logging`.

**Tech Stack:** Python 3.14, stdlib `logging`, pytest plain functions with
`caplog` (built into pytest, not an added dependency).

**Spec:** `src/huginn/ingestion/service.py` (the TODO this ticket resolves),
`src/huginn/ops/job_runs.py` (`JobRunStatus`, `JobRun`, `start_job_run`,
`finish_job_run`, `JobRunWriterPort`, all already merged per KAN-27),
`src/huginn/ingestion/ports.py` (`SourcePort`, `RawStorePort`, `RawRecord`),
`docs/architecture.md` section 5 (ingestion ports-and-adapters), `adr/0005-
logging-required-from-day-one.md`, `CLAUDE.md`, `BEST_PRACTICES.md`.

## Global Constraints

1. **Scope boundary vs. KAN-27**: `JobRun`, `start_job_run`, `finish_job_run`,
   and `JobRunWriterPort` already exist and are frozen contracts from KAN-27.
   This ticket does not modify `src/huginn/ops/job_runs.py` at all, and does
   not write a concrete `JobRunWriterPort` implementation (no Postgres
   adapter) — a Protocol with zero implementations is normal here (`CLAUDE.md`
   code standard 2).
2. **`IngestionService.__init__` gains one new required parameter**,
   `job_run_writer: JobRunWriterPort`, added after the existing `raw_store`
   parameter. There are no existing callers in the codebase to update
   (confirmed: no `IngestionService(` call sites outside this ticket's own
   tests), so this is not a breaking-change concern for this ticket.
3. **What "one source" covers**: the try/except boundary wraps both
   `source.fetch()` and `raw_store.write(...)` for that source, not `fetch()`
   alone. Ruling: the ticket's own language ("one source's adapter throwing
   must not abort the other source's fetch") describes the failure mode by
   example, but the job_runs row exists to record that source's ingestion
   outcome for the run, and a write failure is exactly as much "that source's
   problem" as a fetch failure. Isolating only `fetch()` and leaving a
   `raw_store.write()` exception unhandled would silently reintroduce the bug
   this ticket exists to close.
4. **Exception width: catch `Exception`, not `BaseException`, not a narrower
   type.** This is a deliberate, scoped exception to `BEST_PRACTICES.md`
   section 10.2's "catching `Exception` broadly is a pitfall" guidance: that
   guidance is about swallowing errors "to be safe" when a narrower type is
   knowable in advance. Here the narrower type is not knowable — adapters are
   arbitrary, unbounded implementations of `SourcePort` (HN raises
   `requests.RequestException`/`RuntimeError` today, YC will raise whatever
   Algolia's client raises, a future source could raise anything) — and the
   ticket's explicit contract is "one source's adapter throwing must not
   abort the other source's fetch," which requires catching whatever that
   adapter throws. `KeyboardInterrupt`/`SystemExit` (which subclass
   `BaseException`, not `Exception`) still propagate, so this is not a bare
   `except:`.
5. **`job_run_writer.write(...)` is called exactly once per source per run**,
   with the terminal (`SUCCEEDED`/`FAILED`) `JobRun`, not once at
   `start_job_run` and again at `finish_job_run`. Ruling: `JobRunWriterPort
   .write`'s own docstring allows either "a row (or row update)," and nothing
   in this ticket's scope (per Jira description) asks for live
   still-running visibility into `ops.job_runs` mid-run — only "record the
   failure on that source's job_runs row." Writing once with the final state
   is the minimal contract that satisfies that.
6. **Logging, per ADR-0005**: one module logger,
   `logger = logging.getLogger(__name__)`, no `logging.basicConfig()` call
   anywhere in `src/huginn/`. Log points: run start (source count), each
   source's success (`logger.info`, rows written), each source's failure
   (`logger.exception`, inside the `except` block, exactly once, matching
   `BEST_PRACTICES.md` section 6.2's "log once, at the point that handles
   it"), and run finish (succeeded/failed counts).
7. **`run_once()` keeps its existing `-> None` return type.** Callers that
   need per-source outcomes read `ops.job_runs` (via `job_run_writer`) or the
   log, not a return value — no test in this plan asserts a return value from
   `run_once()`.
8. **Tests are plain pytest functions** (`CLAUDE.md` code standard 4). Use
   pytest's built-in `caplog` fixture for log assertions; no added mocking
   library. Test doubles for `SourcePort`, `RawStorePort`, and
   `JobRunWriterPort` are small hand-written classes in the test file, not a
   framework-generated mock.
9. **TDD is mandatory**: failing test first, watch it fail, minimal code to
   pass (`CLAUDE.md` code standard 5).
10. **No linter, formatter, or type checker is configured.** Don't add one as
    part of this task (`CLAUDE.md` code standard 7).
11. **Docstrings cite, they don't restate** (`CLAUDE.md` code standard 3).
    Point at `docs/architecture.md` section 5 or `adr/0005-logging-required-
    from-day-one.md`, not a paraphrase.
12. **Do not retrofit logging into `src/huginn/ops/job_runs.py` or
    `src/huginn/ingestion/adapters/hn.py`.** ADR-0005 names both as tracked
    debt from before logging was required; that retrofit is separate debt,
    out of this ticket's scope (`CLAUDE.md` code standard 6: build only your
    ticket's part).

---

## Task 1: Wire `job_run_writer` and record a successful per-source run

**Files:**
- Modify: `src/huginn/ingestion/service.py`
- Test: `tests/ingestion/test_service.py` (new file)

**Interfaces:**
- Consumes: `huginn.ingestion.ports.RawRecord`, `SourcePort`, `RawStorePort`
  (existing, unchanged); `huginn.ops.job_runs.JobRunStatus`, `JobRun`,
  `start_job_run(source: str) -> JobRun`,
  `finish_job_run(job_run: JobRun, status: str, rows_written: int = 0, error: str | None = None) -> JobRun`,
  `JobRunWriterPort` (all existing, unchanged, from KAN-27).
- Produces: `IngestionService.__init__(self, sources: list[SourcePort], raw_store: RawStorePort, job_run_writer: JobRunWriterPort) -> None`.
  Task 2 and Task 3 both construct `IngestionService` with this three-argument
  signature; no later task changes it.

- [ ] **Step 1: Write the failing test**

Create `tests/ingestion/test_service.py`:

```python
from __future__ import annotations

from huginn.ingestion.ports import RawRecord
from huginn.ingestion.service import IngestionService
from huginn.ops.job_runs import JobRunStatus


class FakeSource:
    def __init__(self, source: str, records: list[RawRecord]) -> None:
        self.source = source
        self.mechanism = "api"
        self._records = records
        self.fetch_calls = 0

    def fetch(self) -> list[RawRecord]:
        self.fetch_calls += 1
        return self._records


class FakeRawStore:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str, list[RawRecord], str]] = []

    def write(self, source: str, mechanism: str, records: list[RawRecord], run_id: str) -> None:
        self.writes.append((source, mechanism, records, run_id))


class FakeJobRunWriter:
    def __init__(self) -> None:
        self.written = []

    def write(self, job_run) -> None:
        self.written.append(job_run)


def test_run_once_writes_fetched_records_to_raw_store():
    records = [RawRecord(stable_id="1", payload={"id": 1})]
    source = FakeSource("hn", records)
    raw_store = FakeRawStore()
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], raw_store, job_run_writer)

    service.run_once()

    assert len(raw_store.writes) == 1
    written_source, written_mechanism, written_records, _run_id = raw_store.writes[0]
    assert written_source == "hn"
    assert written_mechanism == "api"
    assert written_records == records


def test_run_once_writes_a_succeeded_job_run_for_a_successful_source():
    records = [RawRecord(stable_id="1", payload={"id": 1}), RawRecord(stable_id="2", payload={"id": 2})]
    source = FakeSource("hn", records)
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], FakeRawStore(), job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 1
    job_run = job_run_writer.written[0]
    assert job_run.source == "hn"
    assert job_run.status == JobRunStatus.SUCCEEDED
    assert job_run.rows_written == 2
    assert job_run.error is None
    assert job_run.finished_at is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_service.py -v`
Expected: FAIL — `TypeError: IngestionService.__init__() missing 1 required
positional argument: 'job_run_writer'` (or similar, since the current
`__init__` only takes `sources` and `raw_store`).

- [ ] **Step 3: Write the minimal implementation**

Replace `src/huginn/ingestion/service.py` with:

```python
"""IngestionService: the logic that would otherwise be reimplemented per
adapter. See architecture document section 5.

Holds which sources to fetch, in what order, and when a run counts as
complete. Adapters own a single protocol each and no ingestion policy.
Orchestration itself (cron plus a `job_runs` table, Jira KAN-9) is not
this class's concern; something external calls `run_once` on a schedule.
"""

from __future__ import annotations

import uuid

from huginn.ingestion.ports import RawStorePort, SourcePort
from huginn.ops.job_runs import JobRunStatus, JobRunWriterPort, finish_job_run, start_job_run


class IngestionService:
    def __init__(
        self,
        sources: list[SourcePort],
        raw_store: RawStorePort,
        job_run_writer: JobRunWriterPort,
    ) -> None:
        self._sources = sources
        self._raw_store = raw_store
        self._job_run_writer = job_run_writer

    def run_once(self) -> None:
        """Fetch every configured source once and write results to Bronze.

        See architecture document section 5. Each source gets its own
        `job_runs` row (`huginn.ops.job_runs`); this method does not yet
        isolate one source's failure from the next (Task 2).
        """
        run_id = str(uuid.uuid4())
        for source in self._sources:
            job_run = start_job_run(source.source)
            records = source.fetch()
            self._raw_store.write(source.source, source.mechanism, records, run_id)
            job_run = finish_job_run(job_run, JobRunStatus.SUCCEEDED, rows_written=len(records))
            self._job_run_writer.write(job_run)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_service.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/service.py tests/ingestion/test_service.py
git commit -m "feat(ingestion): wire IngestionService.run_once to job_runs for the success path"
```

---

## Task 2: Per-source error isolation with a failed job_runs row

**Files:**
- Modify: `src/huginn/ingestion/service.py`
- Test: `tests/ingestion/test_service.py`

**Interfaces:**
- Consumes: `IngestionService.__init__` (Task 1, unchanged signature),
  `FakeSource`, `FakeRawStore`, `FakeJobRunWriter` (Task 1, this task adds a
  `FakeFailingSource` and a `FakeFailingRawStore` alongside them in the same
  test file).
- Produces: no new public interface; `run_once()`'s behavior changes from
  "a raising source aborts the run" to "a raising source's exception is
  caught, converted to a `FAILED` job_runs row, and the loop continues."
  Task 3 (logging) builds directly on this task's `except` block.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingestion/test_service.py`:

```python
class FakeFailingSource:
    def __init__(self, source: str, exc: Exception) -> None:
        self.source = source
        self.mechanism = "api"
        self._exc = exc

    def fetch(self):
        raise self._exc


class FakeFailingRawStore:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.writes = []

    def write(self, source, mechanism, records, run_id):
        raise self._exc


def test_run_once_isolates_a_failing_source_and_still_runs_the_next_one():
    good_records = [RawRecord(stable_id="1", payload={"id": 1})]
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    good_source = FakeSource("yc", good_records)
    raw_store = FakeRawStore()
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([failing_source, good_source], raw_store, job_run_writer)

    service.run_once()

    assert good_source.fetch_calls == 1
    assert len(raw_store.writes) == 1
    assert raw_store.writes[0][0] == "yc"


def test_run_once_records_a_failed_job_run_for_a_raising_fetch():
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([failing_source], FakeRawStore(), job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 1
    job_run = job_run_writer.written[0]
    assert job_run.source == "hn"
    assert job_run.status == JobRunStatus.FAILED
    assert job_run.rows_written == 0
    assert job_run.error == "boom"
    assert job_run.finished_at is not None


def test_run_once_records_a_failed_job_run_for_a_raising_raw_store_write():
    records = [RawRecord(stable_id="1", payload={"id": 1})]
    source = FakeSource("hn", records)
    raw_store = FakeFailingRawStore(RuntimeError("disk full"))
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], raw_store, job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 1
    job_run = job_run_writer.written[0]
    assert job_run.status == JobRunStatus.FAILED
    assert job_run.error == "disk full"


def test_run_once_does_not_abort_when_the_last_source_fails():
    good_records = [RawRecord(stable_id="1", payload={"id": 1})]
    good_source = FakeSource("yc", good_records)
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    raw_store = FakeRawStore()
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([good_source, failing_source], raw_store, job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 2
    statuses = {job_run.source: job_run.status for job_run in job_run_writer.written}
    assert statuses == {"yc": JobRunStatus.SUCCEEDED, "hn": JobRunStatus.FAILED}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_service.py -v`
Expected: FAIL — the two isolation tests fail because the failing source's
exception currently propagates out of `run_once()` and aborts the loop
(`RuntimeError: boom` surfaces from the test itself instead of being
caught), so `good_source.fetch_calls` never reaches 1 and no `FAILED` job
run is ever written.

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/ingestion/service.py`, replace the `run_once` method body:

```python
    def run_once(self) -> None:
        """Fetch every configured source once and write results to Bronze.

        One source's `fetch()` or `raw_store.write()` raising does not abort
        the run: the exception is caught, recorded on that source's
        `job_runs` row as `FAILED`, and the loop continues to the next
        source. See architecture document section 5 and `adr/0005-logging-
        required-from-day-one.md`.
        """
        run_id = str(uuid.uuid4())
        for source in self._sources:
            job_run = start_job_run(source.source)
            try:
                records = source.fetch()
                self._raw_store.write(source.source, source.mechanism, records, run_id)
            except Exception as exc:
                job_run = finish_job_run(job_run, JobRunStatus.FAILED, error=str(exc))
                self._job_run_writer.write(job_run)
                continue
            job_run = finish_job_run(job_run, JobRunStatus.SUCCEEDED, rows_written=len(records))
            self._job_run_writer.write(job_run)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_service.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/service.py tests/ingestion/test_service.py
git commit -m "fix(ingestion): isolate a failing source's fetch/write from the rest of the run"
```

---

## Task 3: Logging at run and per-source boundaries (ADR-0005)

**Files:**
- Modify: `src/huginn/ingestion/service.py`
- Test: `tests/ingestion/test_service.py`

**Interfaces:**
- Consumes: `IngestionService` as left by Task 2 (unchanged public signature).
- Produces: no new public interface. `service.py` gains a module-level
  `logger = logging.getLogger(__name__)`, used at four points in `run_once`:
  run start, per-source success, per-source failure (`logger.exception`),
  run finish. This is the final task in this plan; nothing later depends on
  the exact log message text.

- [ ] **Step 1: Write the failing tests**

Append to `tests/ingestion/test_service.py`:

```python
import logging


def test_run_once_logs_an_exception_for_a_failing_source(caplog):
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    service = IngestionService([failing_source], FakeRawStore(), FakeJobRunWriter())

    with caplog.at_level(logging.ERROR, logger="huginn.ingestion.service"):
        service.run_once()

    assert any(
        record.levelname == "ERROR" and "hn" in record.message and record.exc_info is not None
        for record in caplog.records
    )


def test_run_once_logs_run_start_and_finish(caplog):
    good_source = FakeSource("yc", [RawRecord(stable_id="1", payload={"id": 1})])
    service = IngestionService([good_source], FakeRawStore(), FakeJobRunWriter())

    with caplog.at_level(logging.INFO, logger="huginn.ingestion.service"):
        service.run_once()

    messages = [record.message for record in caplog.records]
    assert any("starting" in message and "1" in message for message in messages)
    assert any("finished" in message for message in messages)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/ingestion/test_service.py -v`
Expected: FAIL — no log records are emitted yet at any level, so both
`any(...)` assertions are `False`.

- [ ] **Step 3: Write the minimal implementation**

Replace `src/huginn/ingestion/service.py` with:

```python
"""IngestionService: the logic that would otherwise be reimplemented per
adapter. See architecture document section 5.

Holds which sources to fetch, in what order, and when a run counts as
complete. Adapters own a single protocol each and no ingestion policy.
Orchestration itself (cron plus a `job_runs` table, Jira KAN-9) is not
this class's concern; something external calls `run_once` on a schedule.
Logging follows `adr/0005-logging-required-from-day-one.md`: one logger per
module, no handler configuration here, log at the run and per-source
boundaries.
"""

from __future__ import annotations

import logging
import uuid

from huginn.ingestion.ports import RawStorePort, SourcePort
from huginn.ops.job_runs import JobRunStatus, JobRunWriterPort, finish_job_run, start_job_run

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        sources: list[SourcePort],
        raw_store: RawStorePort,
        job_run_writer: JobRunWriterPort,
    ) -> None:
        self._sources = sources
        self._raw_store = raw_store
        self._job_run_writer = job_run_writer

    def run_once(self) -> None:
        """Fetch every configured source once and write results to Bronze.

        One source's `fetch()` or `raw_store.write()` raising does not abort
        the run: the exception is caught, recorded on that source's
        `job_runs` row as `FAILED`, and the loop continues to the next
        source. See architecture document section 5 and `adr/0005-logging-
        required-from-day-one.md`.
        """
        run_id = str(uuid.uuid4())
        logger.info("run_once starting for %d source(s), run_id=%s", len(self._sources), run_id)

        succeeded_count = 0
        failed_count = 0
        for source in self._sources:
            job_run = start_job_run(source.source)
            try:
                records = source.fetch()
                self._raw_store.write(source.source, source.mechanism, records, run_id)
            except Exception as exc:
                logger.exception("source %s: run failed", source.source)
                job_run = finish_job_run(job_run, JobRunStatus.FAILED, error=str(exc))
                self._job_run_writer.write(job_run)
                failed_count += 1
                continue
            job_run = finish_job_run(job_run, JobRunStatus.SUCCEEDED, rows_written=len(records))
            self._job_run_writer.write(job_run)
            logger.info("source %s: succeeded, wrote %d record(s)", source.source, len(records))
            succeeded_count += 1

        logger.info(
            "run_once finished, run_id=%s: %d succeeded, %d failed",
            run_id,
            succeeded_count,
            failed_count,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/ingestion/test_service.py -v`
Expected: PASS (8 passed)

Then run the full suite to confirm no regressions:

Run: `uv run pytest -q`
Expected: PASS, all tests green (31 pre-existing + 8 new = 39)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/ingestion/service.py tests/ingestion/test_service.py
git commit -m "feat(ingestion): log run/per-source start, success, and failure per ADR-0005"
```

---

## Post-plan note

This plan implements KAN-28 only. It does not add a concrete
`JobRunWriterPort` implementation (no Postgres adapter exists yet, matching
`RawStorePort`/`StatePort`), does not retrofit logging into
`src/huginn/ops/job_runs.py` or `src/huginn/ingestion/adapters/hn.py` (ADR-
0005 tracks both as separate debt), and does not touch the YC adapter
(KAN-30, still blocked on KAN-7). `docs/architecture.md` section 5 and ADR-
0005 are the only architecture-level references this plan draws on; nothing
here revises either.
