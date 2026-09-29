import logging

import pytest

from huginn.elt.bronze.watermark import compute_content_hash
from huginn.elt.bronze.web_scrape_ingest_store import PostgresWebScrapeIngestStore
from huginn.elt.ingestion.models import RawRecord


class _FakeWebScrapeIngestRepository:
    bronze_table = "web_scrape_ingest"

    def __init__(self, lookup_results):
        self._lookup_results = list(lookup_results)
        self.calls = []
        self.enter_count = 0
        self.exit_count = 0

    def __enter__(self):
        self.enter_count += 1
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.exit_count += 1
        return None

    def lookup_hash(self, source, stable_id):
        self.calls.append(("lookup_hash", source, stable_id))
        return self._lookup_results.pop(0)

    def write(self, source, stable_id, payload, content_hash, run_id):
        self.calls.append(("write", source, stable_id, payload, content_hash, run_id))

    def touch(self, source, stable_id):
        self.calls.append(("touch", source, stable_id))


def test_store_rejects_a_repository_for_another_bronze_table():
    class _WrongRepository:
        bronze_table = "api_ingest"

    with pytest.raises(ValueError, match="bronze.web_scrape_ingest"):
        PostgresWebScrapeIngestStore(_WrongRepository())


def test_write_inserts_new_web_scrape_record():
    repository = _FakeWebScrapeIngestRepository([None])
    store = PostgresWebScrapeIngestStore(repository)
    payload = {"url": "https://www.eu-startups.com/directory/brightroom/"}
    run_id = "11111111-1111-1111-1111-111111111111"

    written = store.write(
        "directory_source",
        "web_scrape",
        [RawRecord(stable_id="brightroom", payload=payload)],
        run_id,
    )

    assert repository.calls[0] == ("lookup_hash", "directory_source", "brightroom")
    assert repository.calls[1][:4] == (
        "write",
        "directory_source",
        "brightroom",
        payload,
    )
    assert repository.calls[1][5] == run_id
    assert written == 1


def test_write_uses_presence_aware_configured_stable_fields():
    payload = {
        "html": "<main>Brightroom</main>",
        "lastmod": "2026-09-22T10:00:00+00:00",
        "volatile": "ignored",
    }
    stable_fields = ("html", "lastmod", "missing_field")
    repository = _FakeWebScrapeIngestRepository([None])
    store = PostgresWebScrapeIngestStore(
        repository,
        stable_fields_by_source={"directory_source": stable_fields},
    )

    store.write(
        "directory_source",
        "web_scrape",
        [RawRecord(stable_id="brightroom", payload=payload)],
        "11111111-1111-1111-1111-111111111111",
    )

    assert repository.calls[1][4] == compute_content_hash(
        payload,
        stable_fields,
        include_field_presence=True,
    )


def test_write_touches_matching_record_and_writes_changed_record_in_one_batch():
    unchanged = {"html": "unchanged"}
    existing_hash = compute_content_hash(unchanged, sorted(unchanged))
    repository = _FakeWebScrapeIngestRepository([existing_hash, "stale-hash"])
    store = PostgresWebScrapeIngestStore(repository)

    written = store.write(
        "directory_source",
        "web_scrape",
        [
            RawRecord(stable_id="unchanged", payload=unchanged),
            RawRecord(stable_id="changed", payload={"html": "new"}),
        ],
        "11111111-1111-1111-1111-111111111111",
    )

    assert repository.calls[1] == ("touch", "directory_source", "unchanged")
    assert repository.calls[3][0] == "write"
    assert written == 1
    assert repository.enter_count == 1
    assert repository.exit_count == 1


def test_write_rejects_non_web_scrape_mechanism_before_repository_io():
    repository = _FakeWebScrapeIngestRepository([])
    store = PostgresWebScrapeIngestStore(repository)

    with pytest.raises(NotImplementedError):
        store.write(
            "directory_source",
            "api",
            [RawRecord(stable_id="brightroom", payload={})],
            "11111111-1111-1111-1111-111111111111",
        )

    assert repository.enter_count == 0
    assert repository.calls == []


def test_write_rejects_source_owned_by_atomic_discovery_runner():
    repository = _FakeWebScrapeIngestRepository([])
    store = PostgresWebScrapeIngestStore(repository)

    with pytest.raises(ValueError, match="dedicated atomic discovery runner"):
        store.write(
            "eu_startups",
            "web_scrape",
            [RawRecord(stable_id="brightroom", payload={})],
            "11111111-1111-1111-1111-111111111111",
        )

    assert repository.enter_count == 0
    assert repository.calls == []


def test_write_rejects_invalid_run_id_before_repository_io():
    repository = _FakeWebScrapeIngestRepository([])
    store = PostgresWebScrapeIngestStore(repository)

    with pytest.raises(ValueError):
        store.write(
            "directory_source",
            "web_scrape",
            [RawRecord(stable_id="brightroom", payload={})],
            "not-a-uuid",
        )

    assert repository.enter_count == 0
    assert repository.calls == []


def test_write_logs_written_and_skipped_counts(caplog):
    payload = {"html": "unchanged"}
    existing_hash = compute_content_hash(payload, sorted(payload))
    repository = _FakeWebScrapeIngestRepository([None, existing_hash])
    store = PostgresWebScrapeIngestStore(repository)

    with caplog.at_level(logging.INFO):
        store.write(
            "directory_source",
            "web_scrape",
            [
                RawRecord(stable_id="new", payload={"html": "new"}),
                RawRecord(stable_id="unchanged", payload=payload),
            ],
            "11111111-1111-1111-1111-111111111111",
        )

    assert "bronze.web_scrape_ingest" in caplog.text
    assert "1 written" in caplog.text
    assert "1 skipped" in caplog.text
