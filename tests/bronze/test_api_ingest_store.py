from psycopg.types.json import Jsonb

from huginn.bronze.api_ingest_store import (
    ACTION_SKIP,
    ACTION_WRITE,
    build_lookup_query,
    build_touch_query,
    build_write_query,
    decide_write_action,
)


def test_decide_write_action_writes_when_no_existing_row():
    assert decide_write_action(None, "abc123") == ACTION_WRITE


def test_decide_write_action_writes_when_hash_differs():
    assert decide_write_action("old_hash", "new_hash") == ACTION_WRITE


def test_decide_write_action_skips_when_hash_matches():
    assert decide_write_action("same_hash", "same_hash") == ACTION_SKIP


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

    store.write("hn", "api", records, "11111111-1111-1111-1111-111111111111")

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

    store.write("hn", "api", records, "11111111-1111-1111-1111-111111111111")

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

    store.write("hn", "api", records, "11111111-1111-1111-1111-111111111111")

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

    store.write("hn", "api", records, "11111111-1111-1111-1111-111111111111")

    # 2 lookups + 1 write (record 1, no existing row) + 1 touch (record 2, hash match)
    assert len(cursor.executed) == 4
    assert "ON CONFLICT" in cursor.executed[1][0]
    assert "last_checked_at" in cursor.executed[3][0] and "ON CONFLICT" not in cursor.executed[3][0]


def test_write_raises_for_unsupported_mechanism(monkeypatch):
    cursor = _FakeCursor(lookup_results=[])
    _patch_connect(monkeypatch, cursor)
    store = PostgresApiIngestStore("postgresql://example.invalid/huginn")

    with pytest.raises(NotImplementedError):
        store.write(
            "hn",
            "web_scrape",
            [RawRecord(stable_id="1", payload={})],
            "11111111-1111-1111-1111-111111111111",
        )


def test_write_raises_for_non_uuid_run_id(monkeypatch):
    cursor = _FakeCursor(lookup_results=[])
    _patch_connect(monkeypatch, cursor)
    store = PostgresApiIngestStore("postgresql://example.invalid/huginn")

    with pytest.raises(ValueError):
        store.write("hn", "api", [RawRecord(stable_id="1", payload={})], "not-a-uuid")

    # The guard must fire before any DB I/O, matching how the mechanism
    # guard is validated fail-fast (no lookup/write/touch executed).
    assert cursor.executed == []


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
        store.write("hn", "api", records, "11111111-1111-1111-1111-111111111111")

    assert "1 written" in caplog.text
    assert "1 skipped" in caplog.text
