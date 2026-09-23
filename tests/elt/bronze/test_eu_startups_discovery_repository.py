from datetime import UTC, datetime

import pytest

from huginn.elt.bronze.repositories import eu_startups_discovery_repository
from huginn.elt.bronze.repositories.eu_startups_discovery_repository import (
    PostgresEuStartupsDiscoveryRepository,
    committed_watermark,
)
from huginn.elt.ingestion.models import (
    DiscoveryBatch,
    FailedListingOutcome,
    RawRecord,
)


def _failure(status_code: int | None, lastmod: str) -> FailedListingOutcome:
    return FailedListingOutcome(
        url="https://www.eu-startups.com/directory/broken/",
        lastmod=lastmod,
        status_code=status_code,
    )


def test_terminal_failure_no_longer_pins_the_committed_watermark():
    batch = DiscoveryBatch(
        records=(
            RawRecord(
                stable_id="later-success",
                payload={
                    "url": "https://www.eu-startups.com/directory/later-success/",
                    "html": "<main>ok</main>",
                    "lastmod": "2026-09-05T00:00:00+00:00",
                },
            ),
        ),
        proposed_watermark="2026-09-02T23:59:59+00:00",
        failed_listings=(_failure(404, "2026-09-03T00:00:00+00:00"),),
    )

    result = committed_watermark(batch, ())

    assert result == datetime(2026, 9, 5, tzinfo=UTC)


def test_earliest_retryable_failure_pins_watermark_after_terminal_failures():
    batch = DiscoveryBatch(
        records=(),
        proposed_watermark="2026-09-01T23:59:59+00:00",
        failed_listings=(
            _failure(404, "2026-09-02T00:00:00+00:00"),
            FailedListingOutcome(
                url="https://www.eu-startups.com/directory/network-error/",
                lastmod="2026-09-04T00:00:00+00:00",
                status_code=None,
            ),
        ),
    )

    result = committed_watermark(batch, ("2026-09-04T00:00:00+00:00",))

    assert result == datetime(2026, 9, 3, 23, 59, 59, tzinfo=UTC)


def test_commit_batch_rolls_back_and_closes_when_a_statement_fails(monkeypatch):
    class FailingCursor:
        def __init__(self):
            self._last_sql = ""
            self.closed = False

        def execute(self, sql, _params=()):
            self._last_sql = sql
            if "INSERT INTO bronze.eu_startups_discovery_state" in sql:
                raise RuntimeError("simulated watermark write failure")

        def fetchone(self):
            return None

        def fetchall(self):
            return []

        def close(self):
            self.closed = True

    class FakeConnection:
        def __init__(self):
            self.cursor_instance = FailingCursor()
            self.commits = 0
            self.rollbacks = 0
            self.closed = False

        def cursor(self):
            return self.cursor_instance

        def commit(self):
            self.commits += 1

        def rollback(self):
            self.rollbacks += 1

        def close(self):
            self.closed = True

    connection = FakeConnection()
    monkeypatch.setattr(
        eu_startups_discovery_repository.psycopg,
        "connect",
        lambda _database_url: connection,
    )
    batch = DiscoveryBatch(
        records=(
            RawRecord(
                stable_id="rollback-test",
                payload={
                    "url": "https://www.eu-startups.com/directory/rollback-test/",
                    "html": "<main>ok</main>",
                    "lastmod": "2026-09-05T00:00:00+00:00",
                },
            ),
        ),
        proposed_watermark="2026-09-05T00:00:00+00:00",
        failed_listings=(),
    )

    with pytest.raises(RuntimeError, match="watermark write failure"):
        PostgresEuStartupsDiscoveryRepository("postgresql://test").commit_batch(
            batch, "11111111-1111-1111-1111-111111111111"
        )

    assert connection.commits == 0
    assert connection.rollbacks == 1
    assert connection.cursor_instance.closed is True
    assert connection.closed is True
