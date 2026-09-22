from __future__ import annotations

import os
import uuid
from datetime import datetime

import psycopg
import pytest

from huginn.elt.bronze.repositories.eu_startups_discovery_repository import (
    RETRYABLE,
    TERMINAL,
    PostgresEuStartupsDiscoveryRepository,
)
from huginn.elt.ingestion.models import (
    DiscoveryBatch,
    FailedListingOutcome,
    RawRecord,
)

DATABASE_URL = os.environ.get("HUGINN_DATABASE_URL")


def _database_reachable() -> bool:
    if not DATABASE_URL:
        return False
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("SELECT 1")
        return True
    except psycopg.Error:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(),
    reason="Docker/Testcontainers unavailable and no reachable Postgres configured",
)


def _record(stable_id: str, lastmod: str, html: object = "<main>ok</main>"):
    return RawRecord(
        stable_id=stable_id,
        payload={
            "url": f"https://www.eu-startups.com/directory/{stable_id}/",
            "html": html,
            "lastmod": lastmod,
        },
    )


def _failure(url_key: str, lastmod: str, status_code: int | None):
    return FailedListingOutcome(
        url=f"https://www.eu-startups.com/directory/{url_key}/",
        lastmod=lastmod,
        status_code=status_code,
    )


def _isolate_eu_discovery_state(stable_ids: list[str], urls: list[str]):
    with psycopg.connect(DATABASE_URL) as conn:
        previous_state = conn.execute(
            "SELECT watermark, updated_at "
            "FROM bronze.eu_startups_discovery_state WHERE singleton = TRUE"
        ).fetchone()
        conn.execute(
            "DELETE FROM bronze.web_scrape_ingest "
            "WHERE source = 'eu_startups' AND stable_id = ANY(%s)",
            (stable_ids,),
        )
        conn.execute(
            "DELETE FROM bronze.eu_startups_listing_retry WHERE url = ANY(%s)",
            (urls,),
        )
        conn.execute("DELETE FROM bronze.eu_startups_discovery_state")
    return previous_state


def _restore_eu_discovery_state(
    stable_ids: list[str], urls: list[str], previous_state
) -> None:
    with psycopg.connect(DATABASE_URL) as conn:
        conn.execute(
            "DELETE FROM bronze.web_scrape_ingest "
            "WHERE source = 'eu_startups' AND stable_id = ANY(%s)",
            (stable_ids,),
        )
        conn.execute(
            "DELETE FROM bronze.eu_startups_listing_retry WHERE url = ANY(%s)",
            (urls,),
        )
        conn.execute("DELETE FROM bronze.eu_startups_discovery_state")
        if previous_state is not None:
            conn.execute(
                "INSERT INTO bronze.eu_startups_discovery_state "
                "(singleton, watermark, updated_at) VALUES (TRUE, %s, %s)",
                previous_state,
            )


def test_commit_batch_atomically_persists_row_and_watermark():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    stable_id = f"task2-success-{uuid.uuid4()}"
    watermark = "2026-09-05T12:00:00+00:00"
    record = _record(stable_id, watermark)
    previous_state = _isolate_eu_discovery_state([stable_id], [])

    try:
        written = repository.commit_batch(
            DiscoveryBatch((record,), watermark, ()), str(uuid.uuid4())
        )

        with psycopg.connect(DATABASE_URL) as conn:
            stored = conn.execute(
                "SELECT payload FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            ).fetchone()

        assert written == 1
        assert stored[0] == record.payload
        assert repository.read_watermark() == watermark
    finally:
        _restore_eu_discovery_state([stable_id], [], previous_state)


def test_failed_commit_rolls_back_bronze_row_and_watermark_together():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    baseline_id = f"task2-baseline-{uuid.uuid4()}"
    attempted_id = f"task2-attempted-{uuid.uuid4()}"
    invalid_id = f"task2-invalid-{uuid.uuid4()}"
    baseline_watermark = "2026-09-01T00:00:00+00:00"
    attempted_watermark = "2026-09-06T00:00:00+00:00"
    stable_ids = [baseline_id, attempted_id, invalid_id]
    previous_state = _isolate_eu_discovery_state(stable_ids, [])

    try:
        repository.commit_batch(
            DiscoveryBatch(
                (_record(baseline_id, baseline_watermark),),
                baseline_watermark,
                (),
            ),
            str(uuid.uuid4()),
        )

        bad_batch = DiscoveryBatch(
            (
                _record(attempted_id, "2026-09-05T00:00:00+00:00"),
                _record(
                    invalid_id,
                    attempted_watermark,
                    html={"not", "json-serializable"},
                ),
            ),
            attempted_watermark,
            (),
        )

        with pytest.raises(TypeError):
            repository.commit_batch(bad_batch, str(uuid.uuid4()))

        with psycopg.connect(DATABASE_URL) as conn:
            stored_ids = {
                row[0]
                for row in conn.execute(
                    "SELECT stable_id FROM bronze.web_scrape_ingest "
                    "WHERE source = 'eu_startups' AND stable_id = ANY(%s)",
                    ([baseline_id, attempted_id, invalid_id],),
                ).fetchall()
            }

        assert stored_ids == {baseline_id}
        assert repository.read_watermark() == baseline_watermark
    finally:
        _restore_eu_discovery_state(stable_ids, [], previous_state)


def test_retry_count_is_persisted_while_network_and_5xx_remain_retryable():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    url_key = f"task2-retry-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{url_key}/"
    lastmod = "2026-09-05T00:00:00+00:00"
    proposed = "2026-09-04T23:59:59+00:00"
    previous_state = _isolate_eu_discovery_state([], [failure_url])

    try:
        for status_code in (None, 503):
            repository.commit_batch(
                DiscoveryBatch(
                    (), proposed, (_failure(url_key, lastmod, status_code),)
                ),
                str(uuid.uuid4()),
            )

        with psycopg.connect(DATABASE_URL) as conn:
            retry = conn.execute(
                "SELECT attempt_count, terminal_attempt_count, status "
                "FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (failure_url,),
            ).fetchone()

        assert retry == (2, 0, RETRYABLE)
        assert repository.read_watermark() == proposed
    finally:
        _restore_eu_discovery_state([], [failure_url], previous_state)


def test_mixed_failures_use_total_attempt_count_and_current_status():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    url_key = f"task2-mixed-terminal-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{url_key}/"
    lastmod = "2026-09-05T00:00:00+00:00"
    proposed = "2026-09-04T23:59:59+00:00"
    observed = []
    previous_state = _isolate_eu_discovery_state([], [failure_url])

    try:
        for status_code in (503, 404, 410, 503):
            repository.commit_batch(
                DiscoveryBatch(
                    (), proposed, (_failure(url_key, lastmod, status_code),)
                ),
                str(uuid.uuid4()),
            )
            with psycopg.connect(DATABASE_URL) as conn:
                observed.append(
                    conn.execute(
                        "SELECT attempt_count, terminal_attempt_count, "
                        "last_status_code, status "
                        "FROM bronze.eu_startups_listing_retry WHERE url = %s",
                        (failure_url,),
                    ).fetchone()
                )

        assert observed == [
            (1, 0, 503, RETRYABLE),
            (2, 1, 404, RETRYABLE),
            (3, 2, 410, TERMINAL),
            (4, 2, 503, RETRYABLE),
        ]
    finally:
        _restore_eu_discovery_state([], [failure_url], previous_state)


@pytest.mark.parametrize("status_code", [404, 410])
def test_confirmed_missing_listing_terminalizes_on_third_persisted_attempt(
    status_code,
):
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    url_key = f"task2-terminal-{status_code}-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{url_key}/"
    lastmod = "2026-09-05T00:00:00+00:00"
    proposed = "2026-09-04T23:59:59+00:00"
    observed = []
    previous_state = _isolate_eu_discovery_state([], [failure_url])

    try:
        for _attempt in range(3):
            repository.commit_batch(
                DiscoveryBatch(
                    (), proposed, (_failure(url_key, lastmod, status_code),)
                ),
                str(uuid.uuid4()),
            )
            with psycopg.connect(DATABASE_URL) as conn:
                observed.append(
                    conn.execute(
                        "SELECT attempt_count, status "
                        "FROM bronze.eu_startups_listing_retry WHERE url = %s",
                        (failure_url,),
                    ).fetchone()
                )

        assert observed == [(1, RETRYABLE), (2, RETRYABLE), (3, TERMINAL)]
        assert datetime.fromisoformat(repository.read_watermark()) == (
            datetime.fromisoformat(lastmod)
        )
    finally:
        _restore_eu_discovery_state([], [failure_url], previous_state)
