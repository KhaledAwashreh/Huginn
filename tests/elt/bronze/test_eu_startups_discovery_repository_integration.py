from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from queue import Queue
from threading import Event
from time import monotonic

import psycopg
import pytest

from huginn.elt.bronze.repositories import eu_startups_discovery_repository
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


def test_overlapping_discovery_commits_keep_retryable_failure_checkpoint_pinned(
    monkeypatch,
):
    retry_repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    success_repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    failure = _failure(
        f"task2-concurrent-retry-{uuid.uuid4()}", "2026-09-03T00:00:00+00:00", 503
    )
    record = _record(
        f"task2-concurrent-success-{uuid.uuid4()}", "2026-09-06T00:00:00+00:00"
    )
    pinned_watermark = datetime.fromisoformat(failure.lastmod) - timedelta(seconds=1)
    retry_inserted = Event()
    release_retry = Event()
    backend_pids = Queue()
    real_connect = psycopg.connect
    previous_state = _isolate_eu_discovery_state([record.stable_id], [failure.url])

    class PausingRetryCursor(psycopg.Cursor):
        def execute(self, query, params=None, **kwargs):
            result = super().execute(query, params, **kwargs)
            if query == eu_startups_discovery_repository._WRITE_RETRY_SQL:
                retry_inserted.set()
                assert release_retry.wait(timeout=10), (
                    "Retry transaction was not released"
                )
            return result

    def connect_for_commit(database_url):
        connection = real_connect(
            database_url,
            cursor_factory=PausingRetryCursor,
            connect_timeout=5,
            options="-c statement_timeout=10000",
        )
        backend_pids.put(connection.info.backend_pid)
        return connection

    try:
        with real_connect(DATABASE_URL, autocommit=True) as observer:
            with (
                monkeypatch.context() as patch,
                ThreadPoolExecutor(max_workers=2) as pool,
            ):
                patch.setattr(
                    eu_startups_discovery_repository.psycopg,
                    "connect",
                    connect_for_commit,
                )
                try:
                    retry_commit = pool.submit(
                        retry_repository.commit_batch,
                        DiscoveryBatch((), pinned_watermark.isoformat(), (failure,)),
                        str(uuid.uuid4()),
                    )
                    retry_pid = backend_pids.get(timeout=10)
                    assert retry_inserted.wait(timeout=10), (
                        "Retry insert did not execute"
                    )
                    assert (
                        observer.execute(
                            "SELECT 1 FROM bronze.eu_startups_listing_retry WHERE url = %s",
                            (failure.url,),
                        ).fetchone()
                        is None
                    )

                    success_commit = pool.submit(
                        success_repository.commit_batch,
                        DiscoveryBatch((record,), record.payload["lastmod"], ()),
                        str(uuid.uuid4()),
                    )
                    success_pid = backend_pids.get(timeout=10)
                    assert success_pid != retry_pid

                    # Before the fix the success commits past the invisible retry;
                    # after the fix it waits for this transaction's advisory lock.
                    saw_advisory_wait = False
                    deadline = monotonic() + 10
                    while not success_commit.done():
                        saw_advisory_wait = observer.execute(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks "
                            "WHERE pid = %s AND locktype = 'advisory' AND NOT granted) "
                            "AND %s = ANY(pg_blocking_pids(%s))",
                            (success_pid, retry_pid, success_pid),
                        ).fetchone()[0]
                        if saw_advisory_wait:
                            break
                        assert monotonic() < deadline, (
                            "Competing commit neither finished nor waited for the advisory lock"
                        )
                finally:
                    release_retry.set()

                assert retry_commit.result(timeout=10) == 0
                assert success_commit.result(timeout=10) == 1

            retry = observer.execute(
                "SELECT lastmod, attempt_count, last_status_code, status "
                "FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (failure.url,),
            ).fetchone()
            stored = observer.execute(
                "SELECT payload FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (record.stable_id,),
            ).fetchone()

        assert retry == (datetime.fromisoformat(failure.lastmod), 1, 503, RETRYABLE)
        assert stored == (record.payload,)
        assert (
            datetime.fromisoformat(success_repository.read_watermark())
            <= pinned_watermark
        )
        assert success_repository.list_retryable_listings() == (failure,)
        assert saw_advisory_wait
    finally:
        _restore_eu_discovery_state([record.stable_id], [failure.url], previous_state)


def test_rollback_releases_discovery_lock_before_connection_close(monkeypatch):
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    record = _record(
        f"task2-lock-rollback-{uuid.uuid4()}",
        "2026-09-06T00:00:00+00:00",
        html={"not", "json-serializable"},
    )

    with psycopg.connect(DATABASE_URL) as connection:
        with monkeypatch.context() as patch:
            patch.setattr(
                eu_startups_discovery_repository.psycopg,
                "connect",
                lambda _url: connection,
            )
            patch.setattr(connection, "close", lambda: None)
            with pytest.raises(TypeError):
                repository.commit_batch(
                    DiscoveryBatch((record,), record.payload["lastmod"], ()),
                    str(uuid.uuid4()),
                )

        assert (
            connection.execute(
                "SELECT 1 FROM pg_locks "
                "WHERE pid = pg_backend_pid() AND locktype = 'advisory'"
            ).fetchall()
            == []
        )


def test_persisted_retryable_failure_pins_a_later_success_and_is_listable():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    failure_key = f"task2-persisted-retry-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{failure_key}/"
    success_id = f"task2-newer-success-{uuid.uuid4()}"
    failure_lastmod = "2026-09-03T00:00:00+00:00"
    pinned_watermark = "2026-09-02T23:59:59+00:00"
    success_lastmod = "2026-09-06T00:00:00+00:00"
    previous_state = _isolate_eu_discovery_state([success_id], [failure_url])

    try:
        repository.commit_batch(
            DiscoveryBatch(
                (),
                pinned_watermark,
                (_failure(failure_key, failure_lastmod, 503),),
            ),
            str(uuid.uuid4()),
        )

        expected_retry = FailedListingOutcome(
            url=failure_url,
            lastmod=failure_lastmod,
            status_code=503,
        )
        assert repository.list_retryable_listings() == (expected_retry,)

        repository.commit_batch(
            DiscoveryBatch(
                (_record(success_id, success_lastmod),),
                success_lastmod,
                (),
            ),
            str(uuid.uuid4()),
        )

        assert repository.read_watermark() == pinned_watermark
        assert repository.list_retryable_listings() == (expected_retry,)
    finally:
        _restore_eu_discovery_state([success_id], [failure_url], previous_state)


def test_mixed_failures_use_total_attempt_count_and_current_status():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    url_key = f"task2-mixed-terminal-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{url_key}/"
    lastmod = "2026-09-05T00:00:00+00:00"
    proposed = "2026-09-04T23:59:59+00:00"
    observed = []
    previous_state = _isolate_eu_discovery_state([], [failure_url])

    try:
        for status_code in (503, 404, 410):
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
        ]
    finally:
        _restore_eu_discovery_state([], [failure_url], previous_state)


def test_terminal_retry_state_is_sticky_until_a_success_clears_it():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    url_key = f"task2-sticky-terminal-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{url_key}/"
    lastmod = "2026-09-05T00:00:00+00:00"
    proposed = "2026-09-04T23:59:59+00:00"
    previous_state = _isolate_eu_discovery_state([url_key], [failure_url])

    try:
        for status_code in (404, 404, 404, 503):
            repository.commit_batch(
                DiscoveryBatch(
                    (), proposed, (_failure(url_key, lastmod, status_code),)
                ),
                str(uuid.uuid4()),
            )

        with psycopg.connect(DATABASE_URL) as conn:
            retry = conn.execute(
                "SELECT attempt_count, last_status_code, status "
                "FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (failure_url,),
            ).fetchone()

        assert retry == (4, 503, TERMINAL)

        repository.commit_batch(
            DiscoveryBatch((_record(url_key, lastmod),), lastmod, ()),
            str(uuid.uuid4()),
        )

        with psycopg.connect(DATABASE_URL) as conn:
            retry = conn.execute(
                "SELECT status FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (failure_url,),
            ).fetchone()
        assert retry is None
    finally:
        _restore_eu_discovery_state([url_key], [failure_url], previous_state)


def test_newer_listing_version_resets_terminal_retry_cycle():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    url_key = f"task2-new-version-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{url_key}/"
    old_lastmod = "2026-09-05T00:00:00+00:00"
    old_proposed = "2026-09-04T23:59:59+00:00"
    new_lastmod = "2026-09-10T00:00:00+00:00"
    new_proposed = "2026-09-09T23:59:59+00:00"
    previous_state = _isolate_eu_discovery_state([], [failure_url])

    try:
        for _attempt in range(3):
            repository.commit_batch(
                DiscoveryBatch(
                    (), old_proposed, (_failure(url_key, old_lastmod, 404),)
                ),
                str(uuid.uuid4()),
            )

        repository.commit_batch(
            DiscoveryBatch((), new_proposed, (_failure(url_key, new_lastmod, 503),)),
            str(uuid.uuid4()),
        )

        with psycopg.connect(DATABASE_URL) as conn:
            attempt_count, terminal_attempt_count, stored_lastmod, status = (
                conn.execute(
                    "SELECT attempt_count, terminal_attempt_count, lastmod, status "
                    "FROM bronze.eu_startups_listing_retry WHERE url = %s",
                    (failure_url,),
                ).fetchone()
            )

        assert (attempt_count, terminal_attempt_count, status) == (1, 0, RETRYABLE)
        assert stored_lastmod.isoformat() == new_lastmod
        assert repository.read_watermark() == new_proposed
        assert repository.list_retryable_listings() == (
            FailedListingOutcome(failure_url, new_lastmod, 503),
        )
    finally:
        _restore_eu_discovery_state([], [failure_url], previous_state)


@pytest.mark.parametrize("stale_status_code", [None, 404, 410, 503])
def test_stale_listing_failure_preserves_newer_retry_cycle(stale_status_code):
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    url_key = f"task2-stale-version-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{url_key}/"
    old_lastmod = "2026-09-05T00:00:00+00:00"
    new_lastmod = "2026-09-10T00:00:00+00:00"
    new_proposed = "2026-09-09T23:59:59+00:00"
    previous_state = _isolate_eu_discovery_state([], [failure_url])

    def read_retry():
        with psycopg.connect(DATABASE_URL) as conn:
            return conn.execute(
                "SELECT lastmod, attempt_count, terminal_attempt_count, "
                "last_status_code, status, updated_at "
                "FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (failure_url,),
            ).fetchone()

    try:
        for _attempt in range(3):
            repository.commit_batch(
                DiscoveryBatch((), old_lastmod, (_failure(url_key, old_lastmod, 404),)),
                str(uuid.uuid4()),
            )
        assert read_retry()[:-1] == (
            datetime.fromisoformat(old_lastmod),
            3,
            3,
            404,
            TERMINAL,
        )

        repository.commit_batch(
            DiscoveryBatch((), new_proposed, (_failure(url_key, new_lastmod, 503),)),
            str(uuid.uuid4()),
        )
        newer_retry = read_retry()
        assert newer_retry[:-1] == (
            datetime.fromisoformat(new_lastmod),
            1,
            0,
            503,
            RETRYABLE,
        )
        assert repository.read_watermark() == new_proposed

        repository.commit_batch(
            DiscoveryBatch(
                (), old_lastmod, (_failure(url_key, old_lastmod, stale_status_code),)
            ),
            str(uuid.uuid4()),
        )
        assert read_retry() == newer_retry
        assert repository.read_watermark() == new_proposed
        assert repository.list_retryable_listings() == (
            FailedListingOutcome(failure_url, new_lastmod, 503),
        )

        repository.commit_batch(
            DiscoveryBatch((), new_proposed, (_failure(url_key, new_lastmod, 410),)),
            str(uuid.uuid4()),
        )
        assert read_retry()[:-1] == (
            datetime.fromisoformat(new_lastmod),
            2,
            1,
            410,
            RETRYABLE,
        )
        assert repository.read_watermark() == new_proposed
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
