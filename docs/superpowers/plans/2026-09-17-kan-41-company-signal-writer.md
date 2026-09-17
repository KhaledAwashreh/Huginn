# KAN-41: CompanySignal fact writer

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Write one `gold.company_signal` row per `silver.resolved_signals`
row with `key_derivation = 'domain_normalized'`, joined to its `gold.company`
row via `resolved_company_key`/`domain`. Depends on KAN-40's `Company`
writer having already produced the `gold.company` row a signal's fact will
reference (an inner join naturally skips a signal whose company row doesn't
exist yet this run; it gets picked up automatically once `Company` catches
up on a later run, no explicit ordering needed).

**Architecture:** New module `src/huginn/elt/gold/company_signal.py`
(`CompanySignalWriter`, mirrors `company.py`'s shape), a new port
`CompanySignalRepositoryPort` in `src/huginn/elt/gold/ports.py`, a new model
`ResolvedSignalForFact` in `src/huginn/elt/gold/models.py`, and a new
adapter `src/huginn/elt/gold/repositories/company_signal_repository.py`
(`PostgresCompanySignalRepository`).

**Tech Stack:** Python 3.14, `psycopg` (already a dependency), pytest with
hand-rolled fake test doubles (no mocking framework, matching
`tests/elt/gold/test_company.py`'s `FakeCompanyRepository` pattern exactly).

**Spec:** Jira KAN-41 (fetch live with `mcp__atlassian__getJiraIssue`,
`issueIdOrKey: "KAN-41"`, `cloudId: "kawashreh.atlassian.net"` for the
authoritative text; it is intentionally thin, this plan and ADR-0007 fill
the gaps it left open). ADR-0007 (`adr/0007-company-signal-idempotency-key.md`,
already written, read it in full, it is the binding design decision for
this ticket, especially the idempotency-key and `ON CONFLICT` requirements).
`db/schema/gold.sql` (already updated: `gold.company_signal` now has
`source_stable_id` and `UNIQUE (source, source_stable_id)`, read the
current file, don't assume the pre-ADR-0007 shape).
`src/huginn/elt/gold/company.py`, `src/huginn/elt/gold/ports.py`,
`src/huginn/elt/gold/repositories/company_repository.py`, and
`tests/elt/gold/test_company.py`/`test_company_repository.py` (the sibling
writer this plan pattern-matches throughout, read all four before starting).
`db/schema/silver.sql`'s `resolved_signals` table (the read source).

## Global Constraints

1. **Only `key_derivation = 'domain_normalized'` rows produce a fact.**
   Same reasoning `CompanyWriter` already uses for the same filter (a
   placeholder `unresolved:...` key is not a company identity yet): a
   `company_signal` row references `gold.company` via `company_id NOT NULL
   REFERENCES`, so there is no valid company to reference for an
   unresolved signal anyway. Enforce this by the read query's own `WHERE`
   clause (join to `gold.company` inherently filters this: only
   `domain_normalized` rows carry a real domain that can match a
   `gold.company.domain` row), not by application code re-checking
   `key_derivation`.
2. **Event grain, not collapsed.** Unlike `CompanyWriter.write_all()`
   (which deliberately collapses many signals per domain into one
   `gold.company` write, since `Company` holds current state only),
   `CompanySignalWriter` writes one row per `resolved_signals` row, full
   stop. `resolved_signals` is already event grain (`docs/entities.md`'s
   ResolvedSignal, architecture document section 6); `company_signal` stays
   at that same grain, this ticket does not collapse anything.
3. **Idempotent upsert, per ADR-0007.** `ON CONFLICT (source,
   source_stable_id) DO UPDATE` every column except `id` and `ingested_at`
   (which stays at its first-insert value, the column default, never
   reset by the update branch, matching `gold.company.created_at`'s
   existing precedent in `build_upsert_query`). `company_id` is included
   in the `DO UPDATE SET` list: if a company's domain somehow changed
   ownership between runs (unlikely at this project's current scale, but
   cheap to keep correct), the fact should follow the latest resolution,
   not freeze the first one.
4. **The join, not a per-row Python lookup.** Read `company_id` via a SQL
   `JOIN gold.company ON gold.company.domain =
   silver.resolved_signals.resolved_company_key` in the same query that
   reads the signal's other fields, one round trip for the whole batch,
   not `CompanyWriter`'s per-domain `get_company()` pattern (that one
   needs a fresh row-lock per domain for its Type 2 history logic;
   `CompanySignalWriter` has no history logic, a batch read is simpler and
   correct here).
5. **One connection scope for the whole batch**, matching
   `CompanyWriter.write_all()` and `db/schema/gold.sql`'s writers
   generally, not ADR-0006's split-scope exception (that exception exists
   specifically because `SignalResolver.resolve_all()` does live network
   I/O per row; `CompanySignalWriter` does no I/O beyond the database
   itself, so the general one-scope-per-orchestrator rule applies
   unmodified here).
6. **Docstrings cite, don't restate** (`CLAUDE.md` code standard 3). Point
   at ADR-0007, Jira KAN-40/KAN-41, and `docs/entities.md`'s CompanySignal,
   not a restatement of the reasoning already in this plan or the ADR.
7. **TDD mandatory, DB-free unit tests** (`CLAUDE.md` code standards 4, 5).
   `CompanySignalWriter`'s tests use a hand-rolled fake repository
   (`FakeCompanySignalRepository`), matching `test_company.py`'s
   `FakeCompanyRepository` exactly in shape (`enter_count`/`exit_count`,
   a list capturing what was upserted). `PostgresCompanySignalRepository`'s
   own tests mock `psycopg.connect`, matching `test_company_repository.py`'s
   pattern (read that file for the exact fake-cursor/fake-connection style
   before writing this one).
8. **Scope.** Only the five files named in Architecture, plus their test
   files, plus `db/schema/gold.sql` (already done) and this plan's ADR
   (already done). No `__main__.py`/CLI wiring: `CompanyWriter` itself has
   none yet either (confirmed: `grep -rn "CompanyWriter(" src/` matches
   nothing outside tests), so `CompanySignalWriter` staying unwired matches
   the current state of its sibling, not a gap this ticket needs to close.
   No changes to `company.py`, `CompanyRepositoryPort`, or
   `PostgresCompanyRepository`, this ticket adds a new, separate port and
   repository, it does not extend the existing ones (`DomainNormalizedSignal`
   stays exactly what `CompanyWriter` needs, per its own docstring, this
   ticket does not repurpose it for a different shape of data).

---

## Task 1: Model, port, and Postgres repository

**Files:**
- Modify: `src/huginn/elt/gold/models.py` (add `ResolvedSignalForFact`)
- Modify: `src/huginn/elt/gold/ports.py` (add `CompanySignalRepositoryPort`)
- Create: `src/huginn/elt/gold/repositories/company_signal_repository.py`
- Test: create a new file `tests/elt/gold/test_company_signal_repository.py`,
  not `tests/elt/gold/test_company_repository.py` (do not add to the
  existing `Company` repository's test file, this is a distinct repository
  for a distinct table)
- Test: `tests/elt/gold/test_company_signal_repository_integration.py`
  (new file, skip-if-unreachable live-Postgres test, matching
  `test_company_repository_integration.py`'s pattern exactly, read that
  file first for the skip marker and connection-string convention)

**Interfaces:**
- Produces: `ResolvedSignalForFact` (frozen dataclass): `company_id: str`,
  `source: str`, `source_stable_id: str`, `signal_type: str`,
  `source_url: str | None`, `stage: str | None`, `description: str | None`,
  `occurred_at: datetime`.
- Produces: `CompanySignalRepositoryPort` (Protocol): `__enter__`/`__exit__`
  (same inline shape as `CompanyRepositoryPort`, not a shared base class,
  matching `ports.py`'s existing style for this module), `read_signal_facts(self) -> list[ResolvedSignalForFact]`,
  `upsert_signal(self, fact: ResolvedSignalForFact) -> None`.
- Produces: `PostgresCompanySignalRepository(database_url: str)` implementing
  the port above, composing its own `psycopg` connection/cursor exactly like
  `PostgresCompanyRepository` does (do not import or share
  `PostgresConnectionScope` from `huginn.elt.silver.repositories`, Gold's
  existing repositories, e.g. `PostgresCompanyRepository`, each own their
  connection lifecycle inline rather than sharing Silver's helper, match
  that existing Gold-layer convention, not Silver's).

- [ ] **Step 1: Write the failing tests**

Add to `tests/elt/gold/models.py`... no, add to
`tests/elt/gold/test_company_signal_repository.py` (new file):

```python
from __future__ import annotations

from datetime import UTC, datetime

from huginn.elt.gold.models import ResolvedSignalForFact
from huginn.elt.gold.repositories.company_signal_repository import (
    PostgresCompanySignalRepository,
    build_read_signal_facts_query,
    build_upsert_signal_query,
)


class _FakeCursor:
    def __init__(self, fetchall_result=None):
        self._fetchall_result = fetchall_result or []
        self.executed = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchall(self):
        return self._fetchall_result

    def close(self):
        pass


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def _patch_connect(monkeypatch, cursor):
    connection = _FakeConnection(cursor)
    import huginn.elt.gold.repositories.company_signal_repository as module

    monkeypatch.setattr(module.psycopg, "connect", lambda database_url: connection)
    return connection


def _fact(source_stable_id: str = "1") -> ResolvedSignalForFact:
    return ResolvedSignalForFact(
        company_id="c1",
        source="hn",
        source_stable_id=source_stable_id,
        signal_type="hiring",
        source_url="https://example.invalid",
        stage=None,
        description="desc",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_read_signal_facts_maps_rows_to_the_model(monkeypatch):
    row = (
        "c1",
        "hn",
        "1",
        "hiring",
        "https://example.invalid",
        None,
        "desc",
        datetime(2026, 1, 1, tzinfo=UTC),
    )
    cursor = _FakeCursor(fetchall_result=[row])
    _patch_connect(monkeypatch, cursor)
    repo = PostgresCompanySignalRepository("postgresql://example.invalid/huginn")

    with repo:
        facts = repo.read_signal_facts()

    assert facts == [_fact()]


def test_upsert_signal_runs_the_parameterized_upsert_query(monkeypatch):
    cursor = _FakeCursor()
    _patch_connect(monkeypatch, cursor)
    repo = PostgresCompanySignalRepository("postgresql://example.invalid/huginn")

    with repo:
        repo.upsert_signal(_fact())

    sql, params = cursor.executed[-1]
    assert "ON CONFLICT (source, source_stable_id)" in sql
    assert "ingested_at" not in sql.split("DO UPDATE SET")[1]
    assert params == (
        "c1",
        "hn",
        "1",
        "hiring",
        "https://example.invalid",
        None,
        "desc",
        datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_scope_commits_on_clean_exit(monkeypatch):
    cursor = _FakeCursor()
    connection = _patch_connect(monkeypatch, cursor)
    repo = PostgresCompanySignalRepository("postgresql://example.invalid/huginn")

    with repo:
        pass

    assert connection.committed is True
    assert connection.closed is True


def test_build_read_signal_facts_query_joins_on_resolved_company_key():
    sql, params = build_read_signal_facts_query()
    assert "JOIN gold.company" in sql
    assert "resolved_company_key" in sql
    assert "domain_normalized" in sql
    assert params == ()


def test_build_upsert_signal_query_excludes_id_and_ingested_at_from_update():
    sql, params = build_upsert_signal_query(_fact())
    update_clause = sql.split("DO UPDATE SET")[1]
    assert "id = " not in update_clause
    assert "ingested_at" not in update_clause
    assert "company_id = EXCLUDED.company_id" in update_clause
```

Run `uv run pytest tests/elt/gold/test_company_signal_repository.py -v`,
confirm every test fails (nothing exists yet).

- [ ] **Step 2: Implement**

`src/huginn/elt/gold/models.py`: add, after `DomainNormalizedSignal`:

```python
@dataclass(frozen=True)
class ResolvedSignalForFact:
    """One silver.resolved_signals row already joined to its gold.company
    row, ready to become one gold.company_signal row. See docs/entities.md's
    CompanySignal and ADR-0007. Only domain-normalized signals with a
    matching gold.company row produce one of these, enforced by the read
    query's join, not here.
    """

    company_id: str
    source: str
    source_stable_id: str
    signal_type: str
    source_url: str | None
    stage: str | None
    description: str | None
    occurred_at: datetime
```
(add `from datetime import datetime` to this file's imports if not already
present, check the file first.)

`src/huginn/elt/gold/ports.py`: add, after `CompanyRepositoryPort`, before
`EnrichmentCandidatePort`:

```python
class CompanySignalRepositoryPort(Protocol):
    """Persistence contract for Gold company_signal fact writes. See
    ADR-0007 for the idempotency-key design this port's upsert method
    relies on.
    """

    def __enter__(self) -> CompanySignalRepositoryPort: ...

    def __exit__(self, exc_type, exc_value, traceback) -> None: ...

    def read_signal_facts(self) -> list[ResolvedSignalForFact]:
        """Every domain-normalized silver.resolved_signals row already
        joined to its gold.company row. A row with no matching gold.company
        yet (Company hasn't caught up this run) is not returned; it is
        picked up automatically once Company does, no ordering dependency
        needed between the two writers.
        """
        ...

    def upsert_signal(self, fact: ResolvedSignalForFact) -> None:
        """Insert one gold.company_signal row, or update it in place if
        (source, source_stable_id) already exists (ADR-0007). ingested_at
        is never touched by the update branch.
        """
        ...
```
(add `ResolvedSignalForFact` to this file's existing `from
huginn.elt.gold.models import DomainNormalizedSignal` line.)

`src/huginn/elt/gold/repositories/company_signal_repository.py` (new file):
module docstring citing `huginn.elt.gold.ports`, `huginn.elt.gold.company_signal`,
`db/schema/gold.sql`, ADR-0007, matching `company_repository.py`'s module
docstring shape. Implement:
- `_READ_SIGNAL_FACTS_SQL`: `SELECT c.id, rs.source, rs.source_stable_id,
  rs.signal_type, rs.url, rs.stage, rs.description, rs.occurred_on FROM
  silver.resolved_signals rs JOIN gold.company c ON c.domain =
  rs.resolved_company_key WHERE rs.key_derivation = 'domain_normalized'`
  (no `ORDER BY` needed, this writer does not collapse rows the way
  `CompanyWriter` does, order does not affect correctness here).
- `build_read_signal_facts_query() -> tuple[str, tuple]`: returns
  `(_READ_SIGNAL_FACTS_SQL, ())`, matching `build_read_unenriched_company_names_query`'s
  shape (a function even for a query with no parameters, for the test
  pattern above and consistency with this module's sibling).
- `build_upsert_signal_query(fact: ResolvedSignalForFact) -> tuple[str, tuple]`:
  ```sql
  INSERT INTO gold.company_signal
      (company_id, source, source_stable_id, signal_type, source_url, stage, description, occurred_at)
  VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
  ON CONFLICT (source, source_stable_id) DO UPDATE
  SET company_id = EXCLUDED.company_id,
      signal_type = EXCLUDED.signal_type,
      source_url = EXCLUDED.source_url,
      stage = EXCLUDED.stage,
      description = EXCLUDED.description,
      occurred_at = EXCLUDED.occurred_at
  ```
  params: `(fact.company_id, fact.source, fact.source_stable_id,
  fact.signal_type, fact.source_url, fact.stage, fact.description,
  fact.occurred_at)`. Bind parameters only, never string-built SQL
  (`BEST_PRACTICES.md` section 8.1, already true of the query above, keep
  it that way).
- `PostgresCompanySignalRepository`: same `__init__`/`__enter__`/`__exit__`
  shape as `PostgresCompanyRepository` (copy its connection-lifecycle
  code, adjust naming only), `read_signal_facts()` executes
  `build_read_signal_facts_query()` and maps each row to
  `ResolvedSignalForFact` in the same column order as the SELECT,
  `upsert_signal(fact)` executes `build_upsert_signal_query(fact)`.

Run the tests again, confirm all pass.

- [ ] **Step 3: Integration test**

Create `tests/elt/gold/test_company_signal_repository_integration.py`,
matching `test_company_repository_integration.py`'s skip-marker and
connection pattern exactly (read that file first, copy its structure).
One test: insert a `gold.company` row, a `silver.resolved_signals` row
with `key_derivation = 'domain_normalized'` and a matching
`resolved_company_key`, call `read_signal_facts()`, assert the joined row
comes back correctly; call `upsert_signal()` twice with the same
`(source, source_stable_id)` and a changed `description` the second time,
assert only one row exists in `gold.company_signal` after both calls, with
the updated description.

Run `uv run pytest tests/elt/gold/ -v` (both new test files); the
integration test will skip automatically if no live Postgres is reachable,
same as its sibling, that's expected and fine, do not treat a skip as a
failure. Run `uv run ruff check . && uv run ruff format --check .`.

- [ ] **Step 4: Commit**

One commit, message describing what was added (KAN-41, ADR-0007), no
Claude/Anthropic attribution.

---

## Task 2: `CompanySignalWriter`

**Depends on:** Task 1 (`ResolvedSignalForFact`, `CompanySignalRepositoryPort`
must exist).

**Files:**
- Create: `src/huginn/elt/gold/company_signal.py`
- Test: `tests/elt/gold/test_company_signal.py` (new file)

**Interfaces:**
- Consumes: `ResolvedSignalForFact`, `CompanySignalRepositoryPort` (Task 1).
- Produces: `CompanySignalWriter(repository: CompanySignalRepositoryPort)`,
  `write_all(self) -> int` (count of facts written).

- [ ] **Step 1: Write the failing tests**

Create `tests/elt/gold/test_company_signal.py`, mirroring
`tests/elt/gold/test_company.py`'s `FakeCompanyRepository`/test shape:

```python
from __future__ import annotations

from datetime import UTC, datetime

from huginn.elt.gold.company_signal import CompanySignalWriter
from huginn.elt.gold.models import ResolvedSignalForFact


class FakeCompanySignalRepository:
    def __init__(self, facts):
        self._facts = facts
        self.upserted = []
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.exit_count += 1

    def read_signal_facts(self):
        return self._facts

    def upsert_signal(self, fact):
        self.upserted.append(fact)


def _fact(source_stable_id: str = "1", company_id: str = "c1") -> ResolvedSignalForFact:
    return ResolvedSignalForFact(
        company_id=company_id,
        source="hn",
        source_stable_id=source_stable_id,
        signal_type="hiring",
        source_url="https://example.invalid",
        stage=None,
        description="desc",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_write_all_writes_one_fact_per_signal():
    repo = FakeCompanySignalRepository(facts=[_fact("1"), _fact("2")])
    writer = CompanySignalWriter(repo)

    written = writer.write_all()

    assert written == 2
    assert repo.upserted == [_fact("1"), _fact("2")]


def test_write_all_does_not_collapse_multiple_signals_for_the_same_company():
    """Regression: unlike CompanyWriter, this writer stays at event grain,
    two signals for the same company_id both get their own fact row."""
    repo = FakeCompanySignalRepository(
        facts=[_fact("1", company_id="c1"), _fact("2", company_id="c1")]
    )
    writer = CompanySignalWriter(repo)

    written = writer.write_all()

    assert written == 2


def test_write_all_returns_zero_for_an_empty_batch():
    repo = FakeCompanySignalRepository(facts=[])
    writer = CompanySignalWriter(repo)

    assert writer.write_all() == 0
    assert repo.upserted == []


def test_write_all_opens_the_repository_scope_once_for_the_whole_batch():
    repo = FakeCompanySignalRepository(facts=[_fact("1"), _fact("2")])
    writer = CompanySignalWriter(repo)

    writer.write_all()

    assert repo.enter_count == 1
    assert repo.exit_count == 1
```

Run `uv run pytest tests/elt/gold/test_company_signal.py -v`, confirm
every test fails.

- [ ] **Step 2: Implement**

`src/huginn/elt/gold/company_signal.py`:

```python
"""CompanySignal fact writer: wires silver.resolved_signals to
gold.company_signal. Jira KAN-41, ADR-0007, architecture document
section 4.3.
"""

from __future__ import annotations

import logging

from huginn.elt.gold.ports import CompanySignalRepositoryPort

logger = logging.getLogger(__name__)


class CompanySignalWriter:
    """Reads every domain-normalized signal already joined to its
    gold.company row and upserts one gold.company_signal row per signal.
    Jira KAN-41.

    Event grain, not collapsed (Global Constraint 2 of this plan; unlike
    CompanyWriter, which deliberately collapses to one row per domain):
    resolved_signals is already event grain and company_signal stays there.
    """

    def __init__(self, repository: CompanySignalRepositoryPort) -> None:
        self._repository = repository

    def write_all(self) -> int:
        """Upsert every domain-normalized signal's fact row, returning the
        count written. Idempotent per ADR-0007: re-running this after
        Silver's own every-run reprocessing updates existing rows in
        place rather than duplicating them.
        """
        with self._repository:
            facts = self._repository.read_signal_facts()
            for fact in facts:
                self._repository.upsert_signal(fact)
            written = len(facts)

        logger.info("gold.company_signal write_all: %d written", written)
        return written
```

Run the tests again, confirm all pass. Run `uv run pytest` (full suite,
confirm nothing else broke). Run `uv run ruff check . && uv run ruff format --check .`.

- [ ] **Step 3: Commit**

One commit, message describing what was added (KAN-41), no
Claude/Anthropic attribution.
