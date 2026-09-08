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
