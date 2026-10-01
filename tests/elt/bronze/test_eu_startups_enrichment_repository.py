from huginn.elt.bronze.repositories import eu_startups_enrichment_repository as module
from huginn.elt.bronze.repositories.eu_startups_enrichment_repository import (
    PostgresEuStartupsEnrichmentRepository,
    build_mark_searched_query,
    build_record_upsert_query,
)
from huginn.elt.ingestion.models import (
    EnrichmentBatch,
    EnrichmentCandidateOutcome,
    EnrichmentOutcomeStatus,
    RawRecord,
)


def test_record_upsert_binds_values_and_uses_only_stable_payload_fields():
    record = RawRecord(
        stable_id="brightroom",
        payload={
            "url": "https://www.eu-startups.com/directory/brightroom/",
            "html": "<main>Brightroom</main>",
            "lastmod": "2026-09-30T10:00:00+00:00",
        },
    )

    query, params = build_record_upsert_query(
        record,
        "stable-content-hash",
        "7a90c8eb-fb7d-42ab-b08f-25445f9dcc22",
    )

    assert "INSERT INTO bronze.web_scrape_ingest" in query
    assert "ON CONFLICT (source, stable_id) DO UPDATE" in query
    assert "payload ->> 'lastmod'" in query
    assert params[0:2] == ("eu_startups", "brightroom")
    assert params[2].obj == record.payload
    assert params[3:] == (
        "stable-content-hash",
        "7a90c8eb-fb7d-42ab-b08f-25445f9dcc22",
    )


def test_mark_searched_binds_distinct_names_to_all_matching_gold_rows():
    query, params = build_mark_searched_query(("Brightroom", "Varm"))

    assert "UPDATE gold.company" in query
    assert "name = ANY(%s)" in query
    assert "eu_startups_searched_at IS NULL" in query
    assert params == (["Brightroom", "Varm"],)


def test_enrichment_batch_derives_only_definitive_names():
    batch = EnrichmentBatch(
        records=(RawRecord("brightroom", {"url": "u", "html": "h", "lastmod": "x"}),),
        outcomes=(
            EnrichmentCandidateOutcome("Brightroom", EnrichmentOutcomeStatus.ENRICHED),
            EnrichmentCandidateOutcome(
                "Transient", EnrichmentOutcomeStatus.SEARCH_FAILED
            ),
            EnrichmentCandidateOutcome(
                "Brightroom", EnrichmentOutcomeStatus.DUPLICATE_STABLE_ID
            ),
        ),
    )

    assert batch.definitive_names == ("Brightroom",)


class _FakeCursor:
    def __init__(self, *, fail_on_gold_update=False, existing_payload=None):
        self.calls = []
        self.rowcount = 1
        self.fail_on_gold_update = fail_on_gold_update
        self.existing_payload = existing_payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def execute(self, query, params=None):
        self.calls.append((query, params))
        if query == module._LOOKUP_RECORD_SQL:
            self.row = (self.existing_payload,) if self.existing_payload else None
        elif query == module._MARK_SEARCHED_SQL and self.fail_on_gold_update:
            raise RuntimeError("simulated Gold update failure")

    def fetchone(self):
        return getattr(self, "row", None)


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.commits = 0
        self.rollbacks = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.commits += 1
        else:
            self.rollbacks += 1
        return None

    def cursor(self):
        return self._cursor


def _batch():
    return EnrichmentBatch(
        records=(
            RawRecord(
                "brightroom",
                {
                    "url": "https://www.eu-startups.com/directory/brightroom/",
                    "html": "<main>Brightroom</main>",
                    "lastmod": "2026-09-30T10:00:00+00:00",
                },
            ),
        ),
        outcomes=(
            EnrichmentCandidateOutcome("Brightroom", EnrichmentOutcomeStatus.ENRICHED),
        ),
    )


def test_persist_batch_commits_bronze_and_gold_in_one_transaction(monkeypatch):
    cursor = _FakeCursor()
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(module.psycopg, "connect", lambda url: connection)

    written = PostgresEuStartupsEnrichmentRepository(
        "postgresql://test/db"
    ).persist_batch(_batch(), "7a90c8eb-fb7d-42ab-b08f-25445f9dcc22")

    assert written == 1
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert any(
        "INSERT INTO bronze.web_scrape_ingest" in query for query, _ in cursor.calls
    )
    assert any("UPDATE gold.company" in query for query, _ in cursor.calls)


def test_gold_cursor_failure_rolls_back_bronze_write(monkeypatch):
    cursor = _FakeCursor(fail_on_gold_update=True)
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(module.psycopg, "connect", lambda url: connection)

    try:
        PostgresEuStartupsEnrichmentRepository("postgresql://test/db").persist_batch(
            _batch(), "7a90c8eb-fb7d-42ab-b08f-25445f9dcc22"
        )
        raise AssertionError("expected Gold cursor write failure")
    except RuntimeError as exc:
        assert str(exc) == "simulated Gold update failure"

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert any(
        "INSERT INTO bronze.web_scrape_ingest" in query for query, _ in cursor.calls
    )


def test_unchanged_page_preserves_source_lastmod_and_only_touches_checked_at(
    monkeypatch,
):
    """Enrichment lastmod is synthetic; unchanged url/html retains the whole
    stored payload, including a discovery-sourced lastmod.
    """
    discovery_payload = {
        "url": "https://www.eu-startups.com/directory/brightroom/",
        "html": "<main>Brightroom</main>",
        "lastmod": "2026-09-29T10:00:00+00:00",
    }
    cursor = _FakeCursor(existing_payload=discovery_payload.copy())
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(module.psycopg, "connect", lambda url: connection)

    written = PostgresEuStartupsEnrichmentRepository(
        "postgresql://test/db"
    ).persist_batch(_batch(), "7a90c8eb-fb7d-42ab-b08f-25445f9dcc22")

    assert written == 0
    bronze_queries = [
        query for query, _ in cursor.calls if "bronze.web_scrape_ingest" in query
    ]
    assert bronze_queries == [module._LOOKUP_RECORD_SQL, module._TOUCH_RECORD_SQL]
    assert cursor.existing_payload == discovery_payload


def test_newer_discovery_observation_is_touched_but_not_replaced(monkeypatch):
    cursor = _FakeCursor(
        existing_payload={
            "url": "https://www.eu-startups.com/directory/brightroom/",
            "html": "<main>Newer discovery page</main>",
            "lastmod": "2026-10-01T10:00:00+00:00",
        }
    )
    connection = _FakeConnection(cursor)
    monkeypatch.setattr(module.psycopg, "connect", lambda url: connection)

    written = PostgresEuStartupsEnrichmentRepository(
        "postgresql://test/db"
    ).persist_batch(_batch(), "7a90c8eb-fb7d-42ab-b08f-25445f9dcc22")

    assert written == 0
    assert any("SET last_checked_at = now()" in query for query, _ in cursor.calls)
    assert not any(
        "INSERT INTO bronze.web_scrape_ingest" in query for query, _ in cursor.calls
    )
