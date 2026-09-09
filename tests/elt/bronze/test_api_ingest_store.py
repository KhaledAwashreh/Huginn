import logging

import pytest

from huginn.elt.bronze.api_ingest_store import (
    ACTION_SKIP,
    ACTION_WRITE,
    PostgresApiIngestStore,
    decide_write_action,
)
from huginn.elt.ingestion.models import RawRecord


def test_decide_write_action_writes_when_no_existing_row():
    assert decide_write_action(None, "abc123") == ACTION_WRITE


def test_decide_write_action_writes_when_hash_differs():
    assert decide_write_action("old_hash", "new_hash") == ACTION_WRITE


def test_decide_write_action_skips_when_hash_matches():
    assert decide_write_action("same_hash", "same_hash") == ACTION_SKIP


class _FakeApiIngestRepository:
    """Hand-rolled `ApiIngestRepositoryPort` double, not a mocking
    framework (CLAUDE.md code standard 4), matching
    tests/elt/ingestion/test_hn.py's FakeResponse pattern.

    `PostgresApiIngestStore` no longer touches psycopg at all, so the
    boundary worth faking here is the repository port, not a cursor:
    these tests are about which repository calls the write loop makes for
    a given lookup result, and in what order.
    """

    def __init__(self, lookup_results):
        self._lookup_results = list(lookup_results)
        self.calls = []

    def lookup_hash(self, source, stable_id):
        self.calls.append(("lookup_hash", source, stable_id))
        return self._lookup_results.pop(0)

    def write(self, source, stable_id, payload, content_hash, run_id):
        self.calls.append(("write", source, stable_id, payload, content_hash, run_id))

    def touch(self, source, stable_id):
        self.calls.append(("touch", source, stable_id))


def test_write_inserts_new_record_when_no_existing_row():
    repository = _FakeApiIngestRepository(lookup_results=[None])
    store = PostgresApiIngestStore(repository)
    records = [RawRecord(stable_id="1", payload={"title": "Backend Engineer"})]

    written_count = store.write(
        "hn", "api", records, "11111111-1111-1111-1111-111111111111"
    )

    lookup_call, write_call = repository.calls[0], repository.calls[1]
    assert lookup_call == ("lookup_hash", "hn", "1")
    assert write_call[0] == "write"
    assert write_call[1] == "hn"
    assert write_call[2] == "1"
    assert write_call[3] == {"title": "Backend Engineer"}
    assert write_call[5] == "11111111-1111-1111-1111-111111111111"
    assert written_count == 1


def test_write_touches_last_checked_at_when_hash_matches():
    from huginn.elt.bronze.watermark import compute_content_hash

    payload = {"title": "Backend Engineer"}
    existing_hash = compute_content_hash(payload, sorted(payload.keys()))
    repository = _FakeApiIngestRepository(lookup_results=[existing_hash])
    store = PostgresApiIngestStore(repository)
    records = [RawRecord(stable_id="1", payload=payload)]

    written_count = store.write(
        "hn", "api", records, "11111111-1111-1111-1111-111111111111"
    )

    lookup_call, touch_call = repository.calls[0], repository.calls[1]
    assert lookup_call == ("lookup_hash", "hn", "1")
    assert touch_call == ("touch", "hn", "1")
    assert written_count == 0


def test_write_overwrites_when_hash_differs():
    repository = _FakeApiIngestRepository(lookup_results=["stale_hash"])
    store = PostgresApiIngestStore(repository)
    records = [
        RawRecord(stable_id="1", payload={"title": "Backend Engineer (updated)"})
    ]

    store.write("hn", "api", records, "11111111-1111-1111-1111-111111111111")

    assert repository.calls[1][0] == "write"


def test_write_processes_multiple_records_independently():
    from huginn.elt.bronze.watermark import compute_content_hash

    payload_b = {"title": "B"}
    existing_hash_b = compute_content_hash(payload_b, sorted(payload_b.keys()))
    repository = _FakeApiIngestRepository(lookup_results=[None, existing_hash_b])
    store = PostgresApiIngestStore(repository)
    records = [
        RawRecord(stable_id="1", payload={"title": "A"}),
        RawRecord(stable_id="2", payload=payload_b),
    ]

    written_count = store.write(
        "hn", "api", records, "11111111-1111-1111-1111-111111111111"
    )

    # 2 lookups + 1 write (record 1, no existing row) + 1 touch (record 2, hash match)
    assert len(repository.calls) == 4
    assert repository.calls[1][0] == "write"
    assert repository.calls[3] == ("touch", "hn", "2")
    # Only record 1 was actually written; record 2 was a hash-match skip.
    # rows_written on ops.job_runs must reflect this, not len(records).
    assert written_count == 1


def test_write_raises_for_unsupported_mechanism():
    repository = _FakeApiIngestRepository(lookup_results=[])
    store = PostgresApiIngestStore(repository)

    with pytest.raises(NotImplementedError):
        store.write(
            "hn",
            "web_scrape",
            [RawRecord(stable_id="1", payload={})],
            "11111111-1111-1111-1111-111111111111",
        )


def test_write_raises_for_non_uuid_run_id():
    repository = _FakeApiIngestRepository(lookup_results=[])
    store = PostgresApiIngestStore(repository)

    with pytest.raises(ValueError):
        store.write("hn", "api", [RawRecord(stable_id="1", payload={})], "not-a-uuid")

    # The guard must fire before any DB I/O, matching how the mechanism
    # guard is validated fail-fast (no lookup/write/touch issued).
    assert repository.calls == []


def test_write_logs_written_and_skipped_counts(caplog):
    from huginn.elt.bronze.watermark import compute_content_hash

    payload_b = {"title": "B"}
    existing_hash_b = compute_content_hash(payload_b, sorted(payload_b.keys()))
    repository = _FakeApiIngestRepository(lookup_results=[None, existing_hash_b])
    store = PostgresApiIngestStore(repository)
    records = [
        RawRecord(stable_id="1", payload={"title": "A"}),
        RawRecord(stable_id="2", payload=payload_b),
    ]

    with caplog.at_level(logging.INFO):
        store.write("hn", "api", records, "11111111-1111-1111-1111-111111111111")

    assert "1 written" in caplog.text
    assert "1 skipped" in caplog.text
