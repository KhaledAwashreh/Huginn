from __future__ import annotations

import re
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
    # Word-boundary check, not a plain substring: "company_id = " itself
    # contains the substring "id = ", so a naive `"id = " not in
    # update_clause` would be a false positive against the very
    # `company_id` assertion below (ADR-0007 requires company_id in the
    # update branch; the bare surrogate `id` column must not be).
    assert not re.search(r"\bid\s*=", update_clause)
    assert "ingested_at" not in update_clause
    assert "company_id = EXCLUDED.company_id" in update_clause
