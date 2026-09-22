from datetime import UTC, datetime

import pytest

from huginn.elt.bronze.repositories import eu_startups_discovery_repository
from huginn.elt.bronze.repositories.eu_startups_discovery_repository import (
    RETRYABLE,
    TERMINAL,
    ListingRetryState,
    PostgresEuStartupsDiscoveryRepository,
    advance_retry_state,
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


@pytest.mark.parametrize("status_code", [404, 410])
def test_confirmed_gone_listing_terminalizes_on_exactly_third_attempt(status_code):
    state = None

    state = advance_retry_state(state, status_code)
    assert state == ListingRetryState(1, 1, RETRYABLE)

    state = advance_retry_state(state, status_code)
    assert state == ListingRetryState(2, 2, RETRYABLE)

    state = advance_retry_state(state, status_code)
    assert state == ListingRetryState(3, 3, TERMINAL)


@pytest.mark.parametrize("status_code", [None, 500, 503])
def test_transport_and_server_failures_never_terminalize(status_code):
    state = None

    for _attempt in range(5):
        state = advance_retry_state(state, status_code)

    assert state == ListingRetryState(5, 0, RETRYABLE)


def test_only_confirmed_404_and_410_attempts_count_toward_terminalization():
    state = advance_retry_state(None, 404)
    state = advance_retry_state(state, 503)
    state = advance_retry_state(state, None)
    state = advance_retry_state(state, 410)

    assert state == ListingRetryState(4, 2, RETRYABLE)
    assert advance_retry_state(state, 404).status == TERMINAL


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

    result = committed_watermark(batch, (TERMINAL,))

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

    result = committed_watermark(batch, (TERMINAL, RETRYABLE))

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
