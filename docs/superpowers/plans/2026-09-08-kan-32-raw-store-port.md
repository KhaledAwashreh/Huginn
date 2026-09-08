# KAN-32: Postgres-backed RawStorePort Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a concrete `RawStorePort` (`huginn.ingestion.ports.RawStorePort`)
against `bronze.api_ingest` only: compute each record's content hash, look
up the existing `(source, stable_id)` row, and either write (fresh insert
or hash-changed overwrite) or skip-with-touch (hash matches, bump
`last_checked_at` only), per architecture document section 4.1 point 4.

**Architecture:** One new module, `src/huginn/bronze/api_ingest_store.py`,
split into three DB-free pure pieces (hash-compare decision, three SQL
statement builders returning `(sql, params)` tuples) plus one class,
`PostgresApiIngestStore`, that opens a `psycopg` connection per `write()`
call and drives those pure pieces per record. `web_scrape_ingest` and
`newsletter_ingest` are explicitly out of scope (ticket text, and no
adapter uses those mechanisms yet).

**Tech Stack:** Python 3.14, `psycopg[binary]` (already a dependency, no
ORM), stdlib `logging`, pytest with hand-rolled fake test doubles (no
mocking framework), `pytest.ini_options`/stdlib `socket` for the one
skip-if-unreachable live-DB test.

**Spec:** `docs/architecture.md` section 4.1 (points 2-4 especially),
`db/schema/bronze.sql` (`bronze.api_ingest` exact DDL), ADR-0005 (logging
required from day one), ADR-0001 (mechanism-grouped-table reasoning this
design continues), `src/huginn/bronze/watermark.py` (`compute_content_hash`,
consumed not reimplemented), `src/huginn/ingestion/ports.py`
(`RawStorePort`, `RawRecord`), `BEST_PRACTICES.md` section 8 (security:
parameterized queries only).

## Global Constraints

1. **Exact table/columns** (`db/schema/bronze.sql`): `bronze.api_ingest(id
   UUID PK DEFAULT gen_random_uuid(), source TEXT NOT NULL, stable_id TEXT
   NOT NULL, payload JSONB NOT NULL, content_hash TEXT NOT NULL, fetched_at
   TIMESTAMPTZ NOT NULL DEFAULT now(), run_id UUID NOT NULL, last_checked_at
   TIMESTAMPTZ NOT NULL DEFAULT now(), UNIQUE (source, stable_id))`.
2. **Parameterized queries only, no exceptions** (`BEST_PRACTICES.md`
   section 8.1). Every SQL string used in this module is a fixed,
   module-level constant containing only `%s` placeholders; no f-string or
   `.format()` ever combines a variable value into SQL text. `run_id` is
   cast with `%s::uuid` (a cast on a bind placeholder, still fully
   parameterized) since it arrives as a Python `str`
   (`RawStorePort.write`'s signature) but the column is `UUID`.
3. **The `UNIQUE (source, stable_id)` constraint forces upsert semantics,
   not a literal second `INSERT` on a hash change.** The ticket's prose
   ("either insert (new hash) or bump last_checked_at only (matching
   hash)") reads as two outcomes, but a row already existing for
   `(source, stable_id)` with a *different* hash cannot take a second
   plain `INSERT`, that would raise a unique-violation. The two real
   outcomes, matching ADR-0005's own language ("rows written versus rows
   skipped"), are:
   - **write**: no row exists yet, or a row exists but `content_hash`
     differs. Uses `INSERT ... ON CONFLICT (source, stable_id) DO UPDATE`
     so a brand-new key inserts and a changed-hash key overwrites
     `payload`, `content_hash`, `run_id`, `fetched_at`, and
     `last_checked_at` in one atomic statement (also closes the
     look-up-then-write race window a separate `SELECT` then `UPDATE`
     would otherwise leave open).
   - **skip**: a row exists and `content_hash` matches. `UPDATE ... SET
     last_checked_at = now()` only, no `payload`/`content_hash`/`fetched_at`
     change.
4. **`compute_content_hash`'s `stable_fields` argument has no source of
   truth yet.** `watermark.py` documents `stable_fields` as "chosen per
   source by the adapter," but neither `RawRecord` nor `SourcePort` (nor
   any adapter) carries or defines one today (verified: no reference to
   `stable_fields` anywhere outside `watermark.py` and its own test file).
   Resolving that properly (an adapter-level per-source field list feeding
   through the port contract) is out of KAN-32's scope: it would mean
   changing `RawRecord`/`SourcePort`, and no ticket currently owns that
   design. **This plan's call**: hash over the full payload,
   `compute_content_hash(record.payload, sorted(record.payload.keys()))`.
   This still calls the existing function (not a reimplementation), needs
   no change to `ports.py`, and is consistent with Bronze's own "exactly
   as-fetched, no field curation" rule (`CLAUDE.md` design standard 2) — it
   just means no field is excluded as "volatile noise" yet, since no
   adapter has defined one. **Flag, don't silently bury**: if a future
   adapter's payload carries a field that changes on every fetch without
   the content actually changing (a hit counter, a relevance score), this
   default would defeat skip-on-hash-match for that source until a real
   per-source `stable_fields` mechanism exists. Worth a Jira KAN-16 debt
   entry once a second `api` adapter (YC) actually ships.
5. **Mechanism guard.** `PostgresApiIngestStore.write()` only handles
   `mechanism == "api"`. A call with any other mechanism raises
   `NotImplementedError` naming the ticket boundary, rather than silently
   writing to the wrong table or doing nothing. `web_scrape_ingest`/
   `newsletter_ingest` writers are not built, per ticket scope and
   `CLAUDE.md` code standard 6 (scope discipline).
6. **Logging** (ADR-0005): one `logger = logging.getLogger(__name__)` at
   module level, no handler configuration. `write()` logs exactly once per
   call, after the loop, with `source`, `run_id`, count written, count
   skipped, matching ADR-0005's own phrasing ("rows written versus rows
   skipped").
7. **Connection handling.** `PostgresApiIngestStore(database_url: str)`
   takes a connection string via constructor injection, it never reads
   `HUGINN_DATABASE_URL` itself (`config.py` and `load_config()` stay the
   composition root's job, not this port implementation's — no concrete
   caller wires this yet, same situation `HackerNewsAdapter` was in before
   `IngestionService` existed). `write()` opens one `psycopg.connect(...)`
   context manager per call (used as a `with` block: commits on clean
   exit, rolls back on exception, per `psycopg` 3.x's default connection
   context-manager behavior), one cursor, one `SELECT` and one
   `INSERT .. ON CONFLICT`/`UPDATE` per record.
8. **DB-free testing wherever feasible** (`CLAUDE.md` code standard 4).
   The hash-compare decision (`decide_write_action`) and all three SQL
   statement builders are pure functions, fully unit-tested with no
   connection at all. `PostgresApiIngestStore.write()`'s orchestration
   (loop order, which query fires per case, counts, the mechanism guard,
   the log line) is tested by monkeypatching `psycopg.connect` with a
   small hand-rolled fake connection/cursor (same pattern
   `tests/ingestion/test_hn.py` already uses for `requests.get`, not a
   mocking framework). **What that fake cannot verify, and stays untested
   in this pass**: that the SQL actually executes correctly against real
   Postgres (column names/types match, the `ON CONFLICT` target matches
   the real unique constraint, the `::uuid` cast succeeds, JSONB actually
   round-trips `Jsonb`-wrapped payloads). Task 4 adds one integration test
   for this, skipped automatically when no Postgres is reachable — true in
   this sandbox (`.env` absent, no local Postgres, verified during
   planning), so that test will run in skip mode for this pass, not a
   passing verification of real DB behavior. This is a genuine, explicitly
   flagged gap, not a silently skipped one.
9. **No linter/formatter/type checker configured**, don't add one
   (`CLAUDE.md` code standard 7).
10. **TDD mandatory**: failing test first, watch it fail, minimal code to
    pass (`CLAUDE.md` code standard 5).
11. **Docstrings cite, don't restate** (`CLAUDE.md` code standard 3): point
    at `docs/architecture.md` section 4.1, ADR-0005, or this plan's Global
    Constraint 3/4, not a paraphrase.

---

## Task 1: `decide_write_action` — hash-compare decision logic

**Files:**
- Create: `src/huginn/bronze/api_ingest_store.py`
- Test: `tests/bronze/test_api_ingest_store.py` (new file)

**Interfaces:**
- Produces: `decide_write_action(existing_hash: str | None, new_hash: str)
  -> str`, returning one of the module-level constants `ACTION_WRITE`
  (`"write"`) or `ACTION_SKIP` (`"skip"`). Task 3 calls this directly.

- [ ] **Step 1: Write the failing tests**

Create `tests/bronze/test_api_ingest_store.py`:

```python
from huginn.bronze.api_ingest_store import (
    ACTION_SKIP,
    ACTION_WRITE,
    decide_write_action,
)


def test_decide_write_action_writes_when_no_existing_row():
    assert decide_write_action(None, "abc123") == ACTION_WRITE


def test_decide_write_action_writes_when_hash_differs():
    assert decide_write_action("old_hash", "new_hash") == ACTION_WRITE


def test_decide_write_action_skips_when_hash_matches():
    assert decide_write_action("same_hash", "same_hash") == ACTION_SKIP
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bronze/test_api_ingest_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named
'huginn.bronze.api_ingest_store'`

- [ ] **Step 3: Write the minimal implementation**

Create `src/huginn/bronze/api_ingest_store.py`:

```python
"""Postgres-backed RawStorePort for bronze.api_ingest. See architecture
document section 4.1 point 4 (skip-on-hash-match write) and ADR-0005
(logging required from day one).

Only bronze.api_ingest is wired here (Jira KAN-32). web_scrape_ingest and
newsletter_ingest get the same write path once a mechanism using them
exists; no adapter needs it yet.
"""

from __future__ import annotations

import logging

from huginn.ingestion.ports import RawRecord

logger = logging.getLogger(__name__)

ACTION_WRITE = "write"
ACTION_SKIP = "skip"


def decide_write_action(existing_hash: str | None, new_hash: str) -> str:
    """Decide whether a record needs a write (fresh insert or
    hash-changed overwrite) or only a last_checked_at touch.

    See architecture document section 4.1 point 4 and this plan's Global
    Constraint 3: no existing row, or an existing row whose content_hash
    differs, both write; a matching hash only touches last_checked_at.
    Pure decision logic, no I/O (CLAUDE.md code standard 4).
    """
    if existing_hash is None or existing_hash != new_hash:
        return ACTION_WRITE
    return ACTION_SKIP
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bronze/test_api_ingest_store.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/bronze/api_ingest_store.py tests/bronze/test_api_ingest_store.py
git commit -m "feat(bronze): add hash-compare write/skip decision for api_ingest store"
```

---

## Task 2: SQL statement builders

**Files:**
- Modify: `src/huginn/bronze/api_ingest_store.py`
- Test: `tests/bronze/test_api_ingest_store.py`

**Interfaces:**
- Consumes: nothing from Task 1 directly (independent pure functions).
- Produces:
  - `build_lookup_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]`
  - `build_write_query(source: str, stable_id: str, payload: dict, content_hash: str, run_id: str) -> tuple[str, tuple[str, str, Jsonb, str, str]]`
  - `build_touch_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]`

  All three module-level functions in `huginn.bronze.api_ingest_store`.
  Task 3's `PostgresApiIngestStore.write()` calls all three, unpacked as
  `cur.execute(*build_lookup_query(...))`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/bronze/test_api_ingest_store.py`:

```python
from psycopg.types.json import Jsonb

from huginn.bronze.api_ingest_store import (
    build_lookup_query,
    build_touch_query,
    build_write_query,
)


def test_build_lookup_query_is_parameterized_and_scoped_to_source_and_stable_id():
    sql, params = build_lookup_query("hn", "49522897")

    assert "hn" not in sql
    assert "49522897" not in sql
    assert params == ("hn", "49522897")
    assert "content_hash" in sql
    assert "bronze.api_ingest" in sql


def test_build_write_query_is_parameterized_with_jsonb_payload_and_uuid_cast_run_id():
    payload = {"id": 1, "title": "Backend Engineer"}
    sql, params = build_write_query("hn", "49522897", payload, "hash123", "run-uuid-1")

    assert "hn" not in sql
    assert "49522897" not in sql
    assert "hash123" not in sql
    assert "run-uuid-1" not in sql
    assert "ON CONFLICT" in sql
    assert "%s::uuid" in sql
    assert params[0] == "hn"
    assert params[1] == "49522897"
    assert isinstance(params[2], Jsonb)
    assert params[2].obj == payload
    assert params[3] == "hash123"
    assert params[4] == "run-uuid-1"


def test_build_touch_query_only_bumps_last_checked_at():
    sql, params = build_touch_query("hn", "49522897")

    assert "hn" not in sql
    assert "49522897" not in sql
    assert "last_checked_at" in sql
    assert "payload" not in sql
    assert "content_hash" not in sql
    assert params == ("hn", "49522897")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bronze/test_api_ingest_store.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_lookup_query'
from 'huginn.bronze.api_ingest_store'`

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/bronze/api_ingest_store.py`, add near the top imports:

```python
from psycopg.types.json import Jsonb
```

Add module-level SQL constants and builder functions after
`decide_write_action`:

```python
_LOOKUP_SQL = "SELECT content_hash FROM bronze.api_ingest WHERE source = %s AND stable_id = %s"

_WRITE_SQL = """
    INSERT INTO bronze.api_ingest (source, stable_id, payload, content_hash, run_id)
    VALUES (%s, %s, %s, %s, %s::uuid)
    ON CONFLICT (source, stable_id) DO UPDATE
    SET payload = EXCLUDED.payload,
        content_hash = EXCLUDED.content_hash,
        run_id = EXCLUDED.run_id,
        fetched_at = now(),
        last_checked_at = now()
"""

_TOUCH_SQL = "UPDATE bronze.api_ingest SET last_checked_at = now() WHERE source = %s AND stable_id = %s"


def build_lookup_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]:
    """Parameterized SELECT for the stored content_hash of (source,
    stable_id), or no row if never seen. BEST_PRACTICES.md section 8.1:
    bind parameters only, never string-built SQL.
    """
    return _LOOKUP_SQL, (source, stable_id)


def build_write_query(
    source: str, stable_id: str, payload: dict, content_hash: str, run_id: str
) -> tuple[str, tuple[str, str, Jsonb, str, str]]:
    """Parameterized upsert: a fresh (source, stable_id) inserts, an
    existing one with a changed hash overwrites in place. See this plan's
    Global Constraint 3 for why this is an upsert, not a plain INSERT.
    """
    return _WRITE_SQL, (source, stable_id, Jsonb(payload), content_hash, run_id)


def build_touch_query(source: str, stable_id: str) -> tuple[str, tuple[str, str]]:
    """Parameterized UPDATE bumping last_checked_at only, no payload or
    content_hash change, for a hash-match skip. Architecture document
    section 4.1 point 4.
    """
    return _TOUCH_SQL, (source, stable_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bronze/test_api_ingest_store.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/bronze/api_ingest_store.py tests/bronze/test_api_ingest_store.py
git commit -m "feat(bronze): add parameterized SQL builders for api_ingest upsert path"
```

---

## Task 3: `PostgresApiIngestStore.write()` orchestration

**Files:**
- Modify: `src/huginn/bronze/api_ingest_store.py`
- Test: `tests/bronze/test_api_ingest_store.py`

**Interfaces:**
- Consumes: `decide_write_action`, `build_lookup_query`, `build_write_query`,
  `build_touch_query` (Tasks 1-2); `RawRecord` (`huginn.ingestion.ports`,
  existing).
- Produces: `PostgresApiIngestStore` class implementing `RawStorePort`
  (`huginn.ingestion.ports.RawStorePort`): `__init__(self, database_url:
  str) -> None`; `write(self, source: str, mechanism: str, records:
  list[RawRecord], run_id: str) -> None`. This is the final public
  surface; nothing later in this plan consumes it (KAN-32 is a leaf per
  `architecture-notes/kan-21-build-plan.md` — no `IngestionService` wiring
  exists yet, that stays a separate ticket's job, matching how KAN-29 left
  `HackerNewsAdapter.fetch()` unconsumed by design).

- [ ] **Step 1: Write the failing tests**

Append to `tests/bronze/test_api_ingest_store.py`:

```python
import logging

import pytest

from huginn.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.ingestion.ports import RawRecord


class _FakeCursor:
    """Hand-rolled test double, not a mocking framework (CLAUDE.md code
    standard 4), matching tests/ingestion/test_hn.py's FakeResponse
    pattern for the one boundary (psycopg) that genuinely can't be
    exercised without a real connection.
    """

    def __init__(self, lookup_results):
        self._lookup_results = list(lookup_results)
        self.executed = []

    def execute(self, sql, params):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._lookup_results.pop(0)

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
        "huginn.bronze.api_ingest_store.psycopg.connect", lambda database_url: connection
    )
    return connection


def test_write_inserts_new_record_when_no_existing_row(monkeypatch):
    cursor = _FakeCursor(lookup_results=[None])
    _patch_connect(monkeypatch, cursor)
    store = PostgresApiIngestStore("postgresql://example.invalid/huginn")
    records = [RawRecord(stable_id="1", payload={"title": "Backend Engineer"})]

    store.write("hn", "api", records, "run-1")

    lookup_sql, write_sql = cursor.executed[0], cursor.executed[1]
    assert "SELECT" in lookup_sql[0]
    assert "ON CONFLICT" in write_sql[0]
    assert write_sql[1][0] == "hn"
    assert write_sql[1][1] == "1"


def test_write_touches_last_checked_at_when_hash_matches(monkeypatch):
    from huginn.bronze.watermark import compute_content_hash

    payload = {"title": "Backend Engineer"}
    existing_hash = compute_content_hash(payload, sorted(payload.keys()))
    cursor = _FakeCursor(lookup_results=[(existing_hash,)])
    _patch_connect(monkeypatch, cursor)
    store = PostgresApiIngestStore("postgresql://example.invalid/huginn")
    records = [RawRecord(stable_id="1", payload=payload)]

    store.write("hn", "api", records, "run-1")

    lookup_sql, touch_sql = cursor.executed[0], cursor.executed[1]
    assert "SELECT" in lookup_sql[0]
    assert "UPDATE" in touch_sql[0]
    assert "last_checked_at" in touch_sql[0]
    assert "ON CONFLICT" not in touch_sql[0]


def test_write_overwrites_when_hash_differs(monkeypatch):
    cursor = _FakeCursor(lookup_results=[("stale_hash",)])
    _patch_connect(monkeypatch, cursor)
    store = PostgresApiIngestStore("postgresql://example.invalid/huginn")
    records = [RawRecord(stable_id="1", payload={"title": "Backend Engineer (updated)"})]

    store.write("hn", "api", records, "run-1")

    write_sql = cursor.executed[1]
    assert "ON CONFLICT" in write_sql[0]


def test_write_processes_multiple_records_independently(monkeypatch):
    from huginn.bronze.watermark import compute_content_hash

    payload_b = {"title": "B"}
    existing_hash_b = compute_content_hash(payload_b, sorted(payload_b.keys()))
    cursor = _FakeCursor(lookup_results=[None, (existing_hash_b,)])
    _patch_connect(monkeypatch, cursor)
    store = PostgresApiIngestStore("postgresql://example.invalid/huginn")
    records = [
        RawRecord(stable_id="1", payload={"title": "A"}),
        RawRecord(stable_id="2", payload=payload_b),
    ]

    store.write("hn", "api", records, "run-1")

    # 2 lookups + 1 write (record 1, no existing row) + 1 touch (record 2, hash match)
    assert len(cursor.executed) == 4
    assert "ON CONFLICT" in cursor.executed[1][0]
    assert "last_checked_at" in cursor.executed[3][0] and "ON CONFLICT" not in cursor.executed[3][0]


def test_write_raises_for_unsupported_mechanism(monkeypatch):
    cursor = _FakeCursor(lookup_results=[])
    _patch_connect(monkeypatch, cursor)
    store = PostgresApiIngestStore("postgresql://example.invalid/huginn")

    with pytest.raises(NotImplementedError):
        store.write("hn", "web_scrape", [RawRecord(stable_id="1", payload={})], "run-1")


def test_write_logs_written_and_skipped_counts(monkeypatch, caplog):
    from huginn.bronze.watermark import compute_content_hash

    payload_b = {"title": "B"}
    existing_hash_b = compute_content_hash(payload_b, sorted(payload_b.keys()))
    cursor = _FakeCursor(lookup_results=[None, (existing_hash_b,)])
    _patch_connect(monkeypatch, cursor)
    store = PostgresApiIngestStore("postgresql://example.invalid/huginn")
    records = [
        RawRecord(stable_id="1", payload={"title": "A"}),
        RawRecord(stable_id="2", payload=payload_b),
    ]

    with caplog.at_level(logging.INFO):
        store.write("hn", "api", records, "run-1")

    assert "1 written" in caplog.text
    assert "1 skipped" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/bronze/test_api_ingest_store.py -v`
Expected: FAIL — `ImportError: cannot import name 'PostgresApiIngestStore'
from 'huginn.bronze.api_ingest_store'`

- [ ] **Step 3: Write the minimal implementation**

In `src/huginn/bronze/api_ingest_store.py`, add near the top imports:

```python
import psycopg

from huginn.bronze.watermark import compute_content_hash
```

Add the class at the end of the file:

```python
class PostgresApiIngestStore:
    """`RawStorePort` implementation against `bronze.api_ingest` only. See
    architecture document section 4.1 point 4 and this plan's Global
    Constraint 3 (upsert semantics) and Constraint 4 (stable_fields choice).
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def write(self, source: str, mechanism: str, records: list[RawRecord], run_id: str) -> None:
        """See huginn.ingestion.ports.RawStorePort.write. Only mechanism
        "api" is handled (Jira KAN-32 scope; see this plan's Global
        Constraint 5).
        """
        if mechanism != "api":
            raise NotImplementedError(
                f"PostgresApiIngestStore only writes bronze.api_ingest "
                f"('api' mechanism); got mechanism={mechanism!r}. "
                f"web_scrape_ingest and newsletter_ingest are out of scope "
                f"for KAN-32."
            )

        written = 0
        skipped = 0
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                for record in records:
                    content_hash = compute_content_hash(
                        record.payload, sorted(record.payload.keys())
                    )
                    cur.execute(*build_lookup_query(source, record.stable_id))
                    row = cur.fetchone()
                    existing_hash = row[0] if row else None

                    if decide_write_action(existing_hash, content_hash) == ACTION_WRITE:
                        cur.execute(
                            *build_write_query(
                                source, record.stable_id, record.payload, content_hash, run_id
                            )
                        )
                        written += 1
                    else:
                        cur.execute(*build_touch_query(source, record.stable_id))
                        skipped += 1

        logger.info(
            "bronze.api_ingest write source=%s run_id=%s: %d written, %d skipped",
            source,
            run_id,
            written,
            skipped,
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/bronze/test_api_ingest_store.py -v`
Expected: PASS (12 passed)

Then run the full suite:

Run: `uv run pytest -q`
Expected: PASS, all tests green (31 pre-existing + 12 new = 43)

- [ ] **Step 5: Commit**

```bash
git add src/huginn/bronze/api_ingest_store.py tests/bronze/test_api_ingest_store.py
git commit -m "feat(bronze): implement PostgresApiIngestStore.write() against bronze.api_ingest"
```

---

## Task 4: Live-Postgres integration test (skipped when no database is reachable)

**Files:**
- Create: `tests/bronze/test_api_ingest_store_integration.py`

**Interfaces:**
- Consumes: `PostgresApiIngestStore` (Task 3), `RawRecord` (existing). Reads
  `HUGINN_DATABASE_URL` directly via `os.environ.get` (this test file is
  its own composition root; it does not call `huginn.config.load_config`,
  since `load_config` raises if the variable is unset and this test needs
  to skip cleanly instead in that case).
- Produces: nothing new consumed elsewhere. Standalone verification only.

This task documents and exercises the one thing Task 3's fake-cursor tests
structurally cannot check: real SQL against a real `bronze.api_ingest`
table. Per this plan's Global Constraint 8, this sandbox has no reachable
Postgres (no `.env`, no local server, verified during planning), so this
test is expected to run in **skip** mode for this pass. It stays in the
repo so the very next environment with a real database (or the same
environment once one exists) gets real coverage for free, rather than the
gap being silently left with no test at all.

- [ ] **Step 1: Write the test, skipped when unreachable**

Create `tests/bronze/test_api_ingest_store_integration.py`:

```python
"""Live-Postgres integration coverage for PostgresApiIngestStore.write().

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
See docs/superpowers/plans/2026-09-08-kan-32-raw-store-port.md Task 4 and
Global Constraint 8: the fake-cursor unit tests in test_api_ingest_store.py
cannot verify real SQL execution against bronze.api_ingest (column names,
the ON CONFLICT target, the ::uuid cast, JSONB round-tripping). This test
is that verification, gated on a real database actually being present.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

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
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable; see plan Task 4",
)


def test_write_then_write_again_with_same_payload_only_touches_last_checked_at():
    store = PostgresApiIngestStore(DATABASE_URL)
    source = "kan32-integration-test"
    stable_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    payload = {"title": "Integration Test Posting"}
    record = [RawRecord(stable_id=stable_id, payload=payload)]

    try:
        store.write(source, "api", record, run_id)
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, fetched_at FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            first_hash, first_fetched_at = cur.fetchone()

        store.write(source, "api", record, str(uuid.uuid4()))
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, fetched_at, last_checked_at FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            second_hash, second_fetched_at, last_checked_at = cur.fetchone()

        assert second_hash == first_hash
        assert second_fetched_at == first_fetched_at
        assert last_checked_at >= first_fetched_at
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
```

- [ ] **Step 2: Run the test to confirm skip behavior in this environment**

Run: `uv run pytest tests/bronze/test_api_ingest_store_integration.py -v`
Expected: `1 skipped` (no `HUGINN_DATABASE_URL`/no reachable Postgres in
this sandbox). This is the expected, documented outcome for this pass,
not a failure to chase down.

- [ ] **Step 3: Run the full suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: PASS, all previously-passing tests still green, this one file
reporting skipped, not failed or errored.

- [ ] **Step 4: Commit**

```bash
git add tests/bronze/test_api_ingest_store_integration.py
git commit -m "test(bronze): add live-Postgres integration test for api_ingest write path, skipped when unreachable"
```

---

## Post-plan note

This plan implements KAN-32 only: `PostgresApiIngestStore` against
`bronze.api_ingest`. It does not wire `IngestionService` to call this
class (no ticket currently does; `IngestionService.run_once` still expects
an already-constructed `RawStorePort` injected by a caller that doesn't
exist yet), does not touch `StatePort` (KAN-33), and does not build
`web_scrape_ingest`/`newsletter_ingest` writers (ticket text: "no adapter
needs it yet"). The `stable_fields` gap (Global Constraint 4) is a real,
flagged limitation of this pass, not a silent scope decision, worth a
Jira KAN-16 debt entry once a second `api`-mechanism adapter exists to
make the tradeoff concrete.
