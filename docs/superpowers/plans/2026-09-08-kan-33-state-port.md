# KAN-33: Postgres-backed StatePort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a concrete `StatePort` (`huginn.ingestion.ports.StatePort`)
against `bronze.api_ingest`: a thin read returning the stored `content_hash`
for a `(source, stable_id)` pair, or `None` if that pair has never been
seen, for the `RawStorePort` write path (KAN-32) to compare against.

**Architecture:** One new module, `src/huginn/bronze/api_ingest_state.py`,
holding one class, `PostgresApiIngestState`, implementing `StatePort.last_hash`.
It reuses `huginn.bronze.api_ingest_store.build_lookup_query` rather than
duplicating an equivalent SQL string (see Global Constraint 2 for why).
`last_hash()` opens one `psycopg` connection, runs the shared lookup query,
and returns `row[0]` or `None`.

**Tech Stack:** Python 3.14, `psycopg[binary]` (already a dependency, no
ORM), stdlib `logging`, pytest with hand-rolled fake test doubles (no
mocking framework), `pytest.mark.skipif` for the one skip-if-unreachable
live-DB test.

**Spec:** `docs/architecture.md` section 4.1 (point 4, content-hash
watermark) and section 5 (`StatePort`'s role in the ingestion ports
diagram), `db/schema/bronze.sql` (`bronze.api_ingest` exact DDL), ADR-0005
(logging required from day one), `src/huginn/bronze/api_ingest_store.py`
(KAN-32, sibling `RawStorePort` implementation on the same table, source
of the shared `build_lookup_query` helper), `src/huginn/ingestion/ports.py`
(`StatePort` Protocol: `last_hash(self, source: str, stable_id: str) ->
str | None`), `BEST_PRACTICES.md` section 8 (security: parameterized
queries only).

## Global Constraints

1. **Exact table/columns** (`db/schema/bronze.sql`): `bronze.api_ingest(id
   UUID PK DEFAULT gen_random_uuid(), source TEXT NOT NULL, stable_id TEXT
   NOT NULL, payload JSONB NOT NULL, content_hash TEXT NOT NULL, fetched_at
   TIMESTAMPTZ NOT NULL DEFAULT now(), run_id UUID NOT NULL, last_checked_at
   TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE (source, stable_id))`. Only
   `content_hash`, `source`, `stable_id` are read here.
2. **Reuse KAN-32's lookup helper, don't duplicate it.** KAN-32's
   `api_ingest_store.build_lookup_query(source, stable_id)` already builds
   exactly the parameterized query `StatePort.last_hash` needs (`SELECT
   content_hash FROM bronze.api_ingest WHERE source = %s AND stable_id =
   %s`), verified byte-for-byte identical against the ticket's own quoted
   `_LOOKUP_SQL`. **This plan's call**: import and call
   `build_lookup_query` from `huginn.bronze.api_ingest_store` rather than
   writing a second, near-identical SQL constant in the new module.
   Reasoning: the two ports share the same underlying table and the same
   query shape by construction, not by coincidence (the ticket's own
   description says so: "Depends on the RawStorePort subtask sharing the
   same underlying table access"); a duplicated string would silently
   drift the day either query needs a column added, and there is nothing
   port-specific about a `SELECT`, only the two callers' surrounding
   orchestration differs (`RawStorePort.write`'s per-record loop plus
   write/touch decision vs. `StatePort.last_hash`'s single unconditional
   read). The alternative (a new tiny query-building module, or an inlined
   SQL string duplicated in both files) was considered and rejected: it
   buys no independence `RawStorePort` doesn't already have (both still
   read the exact same table and columns) and only adds a second place a
   future schema change must be kept in sync by hand. The import direction
   (`api_ingest_state.py` depends on `api_ingest_store.py`, never the
   reverse) is deliberate: KAN-32 shipped first and owns the table's write
   path; `StatePort`'s read-only implementation is the natural downstream
   consumer of its query builder, not a peer that RawStorePort should ever
   need to import back.
3. **Parameterized queries only, no exceptions** (`BEST_PRACTICES.md`
   section 8.1). This module introduces no new SQL string of its own (see
   Constraint 2); the only query it runs is `build_lookup_query`'s
   existing, already-tested `%s`-only parameterized `SELECT`.
4. **Logging** (ADR-0005): one `logger = logging.getLogger(__name__)` at
   module level, no handler configuration. `last_hash()` logs exactly once
   per call, at **DEBUG** level, recording `source`, `stable_id`, and
   whether the lookup was a hit or a miss. DEBUG, not INFO: unlike
   `RawStorePort.write()` (Constraint reference: KAN-32 plan Constraint 6),
   which logs once per **batch** with aggregate counts, `StatePort.last_hash`
   is a per-entity call a caller may invoke once per record in a fetch
   batch; logging every single call at INFO would flood the log with one
   line per record for a read that, on its own, is not a pipeline-stage
   boundary the way a completed write batch is. DEBUG keeps the visibility
   available (turned on when actually debugging a watermark issue) without
   drowning out the INFO-level signal ADR-0005 is actually meant to
   protect (a stalled or failing run stands out in the log).
5. **Connection handling.** `PostgresApiIngestState(database_url: str)`
   takes a connection string via constructor injection, mirroring
   `PostgresApiIngestStore`; it never reads `HUGINN_DATABASE_URL` itself
   (`config.py`/`load_config()` stays the composition root's job). `last_hash()`
   opens one `psycopg.connect(...)` context manager per call (a `with`
   block, matching `psycopg` 3.x's default commit-on-clean-exit behavior,
   though a read-only `SELECT` never has anything to commit), one cursor,
   one `SELECT`. No adapter or `IngestionService` wiring exists yet for
   this class; that stays a separate ticket's job (same precedent KAN-32's
   plan set for `PostgresApiIngestStore`).
6. **DB-free testing wherever feasible** (`CLAUDE.md` code standard 4).
   `last_hash()`'s orchestration (which query fires, how the row maps to
   `None`/a hash string, the log line) is tested by monkeypatching
   `psycopg.connect` with a small hand-rolled fake connection/cursor,
   local to the new test file per `BEST_PRACTICES.md` section 7.1's
   one-off-fixture rule (matching `test_api_ingest_store.py`'s
   `_FakeCursor`/`_FakeConnection` pattern, not imported from that file,
   since importing test doubles across test files couples two otherwise
   independent test suites for no benefit here). What that fake cannot
   verify, and stays untested in this pass: that the query executes
   correctly against real Postgres. Task 2 adds one integration test for
   this, skipped automatically when no Postgres is reachable, matching
   KAN-32's `test_api_ingest_store_integration.py` pattern exactly.
7. **Scope.** Only `bronze.api_ingest` (KAN-33 ticket text). No
   `web_scrape_ingest`/`newsletter_ingest` state reads (no adapter uses
   those mechanisms yet, same boundary KAN-32 drew). No changes to
   `StatePort`'s Protocol definition, no `IngestionService` wiring, no
   changes to `PostgresApiIngestStore` itself (KAN-32 stays merged as-is;
   this ticket only adds a new downstream consumer of its query builder).
8. **No linter/formatter/type checker configured**, don't add one
   (`CLAUDE.md` code standard 7).
9. **TDD mandatory**: failing test first, watch it fail, minimal code to
   pass (`CLAUDE.md` code standard 5).
10. **Docstrings cite, don't restate** (`CLAUDE.md` code standard 3): point
    at `docs/architecture.md` section 4.1/5, ADR-0005, or this plan's
    Global Constraint 2/4, not a paraphrase.

---

## Task 1: `PostgresApiIngestState.last_hash()` — read against bronze.api_ingest

**Files:**
- Create: `src/huginn/bronze/api_ingest_state.py`
- Test: `tests/bronze/test_api_ingest_state.py` (new file)

**Interfaces:**
- Consumes: `build_lookup_query(source: str, stable_id: str) -> tuple[str,
  tuple[str, str]]` from `huginn.bronze.api_ingest_store` (existing, KAN-32).
- Produces: `PostgresApiIngestState` implementing `StatePort`
  (`huginn.ingestion.ports.StatePort`): `__init__(self, database_url: str)
  -> None`; `last_hash(self, source: str, stable_id: str) -> str | None`.
  This is the final public surface of this plan; nothing later in this
  plan consumes it besides Task 2's integration test.

- [ ] **Step 1: Write the failing tests**

Create `tests/bronze/test_api_ingest_state.py`:

```python
import logging

from huginn.bronze.api_ingest_state import PostgresApiIngestState


class _FakeCursor:
    """Hand-rolled test double, not a mocking framework (CLAUDE.md code
    standard 4), local to this file per BEST_PRACTICES.md section 7.1
    (a one-off fixture belongs next to what uses it, not shared across
    test files). Mirrors test_api_ingest_store.py's fake for the one
    boundary (psycopg) that genuinely can't be exercised without a real
    connection.
    """

    def __init__(self, lookup_result):
        self._lookup_result = lookup_result
        self.executed = []

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._lookup_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def cursor(self):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


def _patch_connect(monkeypatch, cursor):
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(
        "huginn.bronze.api_ingest_state.psycopg.connect", lambda database_url: connection
    )
    return connection


def test_last_hash_returns_none_when_never_seen(monkeypatch):
    cursor = _FakeCursor(lookup_result=None)
    _patch_connect(monkeypatch, cursor)
    state = PostgresApiIngestState("postgresql://example.invalid/huginn")

    result = state.last_hash("hn", "49522897")

    assert result is None


def test_last_hash_returns_stored_hash_when_row_exists(monkeypatch):
    cursor = _FakeCursor(lookup_result=("hash123",))
    _patch_connect(monkeypatch, cursor)
    state = PostgresApiIngestState("postgresql://example.invalid/huginn")

    result = state.last_hash("hn", "49522897")

    assert result == "hash123"


def test_last_hash_runs_the_shared_parameterized_lookup_query(monkeypatch):
    cursor = _FakeCursor(lookup_result=None)
    _patch_connect(monkeypatch, cursor)
    state = PostgresApiIngestState("postgresql://example.invalid/huginn")

    state.last_hash("hn", "49522897")

    assert len(cursor.executed) == 1
    sql, params = cursor.executed[0]
    assert "SELECT" in sql
    assert "content_hash" in sql
    assert "bronze.api_ingest" in sql
    assert params == ("hn", "49522897")
    assert "hn" not in sql
    assert "49522897" not in sql


def test_last_hash_logs_hit_at_debug_level(monkeypatch, caplog):
    cursor = _FakeCursor(lookup_result=("hash123",))
    _patch_connect(monkeypatch, cursor)
    state = PostgresApiIngestState("postgresql://example.invalid/huginn")

    with caplog.at_level(logging.DEBUG):
        state.last_hash("hn", "49522897")

    assert "hit" in caplog.text
    assert "hn" in caplog.text
    assert "49522897" in caplog.text


def test_last_hash_logs_miss_at_debug_level(monkeypatch, caplog):
    cursor = _FakeCursor(lookup_result=None)
    _patch_connect(monkeypatch, cursor)
    state = PostgresApiIngestState("postgresql://example.invalid/huginn")

    with caplog.at_level(logging.DEBUG):
        state.last_hash("hn", "49522897")

    assert "miss" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bronze/test_api_ingest_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named
'huginn.bronze.api_ingest_state'`

- [ ] **Step 3: Write the minimal implementation**

Create `src/huginn/bronze/api_ingest_state.py`:

```python
"""Postgres-backed StatePort: a thin read against bronze.api_ingest for
the last stored content_hash of a (source, stable_id) pair. See
architecture document section 4.1 point 4 (content-hash watermark) and
section 5 (StatePort's role in the ingestion ports diagram). ADR-0005:
logging required from day one.

Shares its lookup query with huginn.bronze.api_ingest_store (Jira KAN-32):
RawStorePort's write path and StatePort's read both need exactly the
"stored content_hash for (source, stable_id)" query against the same
table. See this plan's (Jira KAN-33) Global Constraint 2 for why this
module imports build_lookup_query rather than duplicating it.
"""

from __future__ import annotations

import logging

import psycopg

from huginn.bronze.api_ingest_store import build_lookup_query

logger = logging.getLogger(__name__)


class PostgresApiIngestState:
    """`StatePort` implementation against `bronze.api_ingest` only. See
    architecture document section 4.1 and section 5, and this plan's
    Global Constraint 2 (shared lookup query) and Constraint 4 (DEBUG-level
    per-call logging).
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def last_hash(self, source: str, stable_id: str) -> str | None:
        """See huginn.ingestion.ports.StatePort.last_hash."""
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(*build_lookup_query(source, stable_id))
                row = cur.fetchone()

        result = row[0] if row else None
        logger.debug(
            "bronze.api_ingest lookup source=%s stable_id=%s: %s",
            source,
            stable_id,
            "hit" if result is not None else "miss",
        )
        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bronze/test_api_ingest_state.py -v`
Expected: PASS (5 passed)

Then run the full suite:

Run: `uv run pytest -q`
Expected: PASS, all previously-passing tests still green, 5 new tests
added.

- [ ] **Step 5: Commit**

```bash
git add src/huginn/bronze/api_ingest_state.py tests/bronze/test_api_ingest_state.py
git commit -m "feat(bronze): implement PostgresApiIngestState.last_hash() against bronze.api_ingest"
```

---

## Task 2: Live-Postgres integration test (skipped when no database is reachable)

**Files:**
- Create: `tests/bronze/test_api_ingest_state_integration.py`

**Interfaces:**
- Consumes: `PostgresApiIngestState` (Task 1), `PostgresApiIngestStore` and
  `RawRecord` (existing, KAN-32) to seed a row via the real write path
  before reading it back.
- Produces: nothing new consumed elsewhere. Standalone verification only.

This task exercises the one thing Task 1's fake-cursor tests structurally
cannot check: that the shared lookup query actually executes correctly
against a real `bronze.api_ingest` table (column names, and that a row
written by `PostgresApiIngestStore` is actually visible to
`PostgresApiIngestState.last_hash` afterward). Matching KAN-32's own
Global Constraint 8 finding, this sandbox has no reachable Postgres (no
`.env`, no local server), so this test is expected to run in **skip**
mode for this pass, not a failure to chase down.

- [ ] **Step 1: Write the test, skipped when unreachable**

Create `tests/bronze/test_api_ingest_state_integration.py`:

```python
"""Live-Postgres integration coverage for PostgresApiIngestState.last_hash().

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
See docs/superpowers/plans/2026-09-08-kan-33-state-port.md Task 2 and
Global Constraint 6: the fake-cursor unit tests in
test_api_ingest_state.py cannot verify real SQL execution against
bronze.api_ingest. This test is that verification, gated on a real
database actually being present, matching
tests/bronze/test_api_ingest_store_integration.py's pattern exactly.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from huginn.bronze.api_ingest_state import PostgresApiIngestState
from huginn.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.ingestion.ports import RawRecord

DATABASE_URL = os.environ.get("HUGINN_DATABASE_URL")


def _database_reachable() -> bool:
    if not DATABASE_URL:
        return False
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(),
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable; see plan Task 2",
)


def test_last_hash_returns_none_for_a_pair_never_written():
    state = PostgresApiIngestState(DATABASE_URL)
    source = "kan33-integration-test"
    stable_id = str(uuid.uuid4())

    assert state.last_hash(source, stable_id) is None


def test_last_hash_returns_the_hash_a_prior_write_stored():
    store = PostgresApiIngestStore(DATABASE_URL)
    state = PostgresApiIngestState(DATABASE_URL)
    source = "kan33-integration-test"
    stable_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    payload = {"title": "Integration Test Posting"}

    try:
        store.write(source, "api", [RawRecord(stable_id=stable_id, payload=payload)], run_id)

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            (expected_hash,) = cur.fetchone()

        assert state.last_hash(source, stable_id) == expected_hash
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
```

- [ ] **Step 2: Run the test to confirm skip behavior in this environment**

Run: `uv run pytest tests/bronze/test_api_ingest_state_integration.py -v`
Expected: `2 skipped` (no `HUGINN_DATABASE_URL`/no reachable Postgres in
this sandbox). This is the expected, documented outcome for this pass,
not a failure to chase down.

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: PASS, all previously-passing tests still green, this file
reporting skipped, not failed or errored. Baseline going into this plan
was 64 passed, 1 skipped (master, post-KAN-32); expect 69 passed, 3
skipped after this task (5 new Task 1 unit tests passing, 2 new Task 2
integration tests skipped).

- [ ] **Step 4: Commit**

```bash
git add tests/bronze/test_api_ingest_state_integration.py
git commit -m "test(bronze): add live-Postgres integration test for StatePort.last_hash, skipped when unreachable"
```

---

## Post-plan note

This plan implements KAN-33 only: `PostgresApiIngestState.last_hash()`
against `bronze.api_ingest`. It deliberately reuses KAN-32's
`build_lookup_query` (Global Constraint 2) rather than duplicating an
identical SQL string, on the ticket's own stated rationale ("sharing the
same underlying table access"). It does not touch `PostgresApiIngestStore`
itself, does not wire `IngestionService` or any adapter to call
`PostgresApiIngestState` (no ticket currently owns that composition), and
does not build `web_scrape_ingest`/`newsletter_ingest` state reads (no
adapter uses those mechanisms yet, matching KAN-32's drawn boundary).
