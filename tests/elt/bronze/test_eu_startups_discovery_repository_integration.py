from __future__ import annotations

import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue
from threading import Event
from time import monotonic

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

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
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "db" / "schema"
_KAN_83_UPGRADE = _SCHEMA_DIR / "kan-83-eu-startups-discovery.sql"
_PRE_KAN_83_SCHEMA_FILES = ("00_extensions.sql", "bronze.sql")


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


def _maintenance_database_url() -> str:
    connection_options = conninfo_to_dict(DATABASE_URL)
    connection_options["dbname"] = "postgres"
    return make_conninfo(**connection_options)


def _database_exists(database_name: str) -> bool:
    with psycopg.connect(_maintenance_database_url()) as conn:
        return conn.execute(
            "SELECT EXISTS (SELECT FROM pg_database WHERE datname = %s)",
            (database_name,),
        ).fetchone()[0]


def _configured_database_state():
    with psycopg.connect(DATABASE_URL) as conn:
        return conn.execute(
            "SELECT current_database(), "
            "'bronze.web_scrape_ingest'::regclass::oid, "
            "'bronze.eu_startups_discovery_state'::regclass::oid, "
            "'bronze.eu_startups_listing_retry'::regclass::oid"
        ).fetchone()


def _drop_temporary_database(database_name: str) -> None:
    with psycopg.connect(_maintenance_database_url(), autocommit=True) as conn:
        assert conn.execute("SELECT current_database()").fetchone()[0] == "postgres"
        conn.execute(
            sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                sql.Identifier(database_name)
            )
        )


@contextmanager
def _temporary_pre_kan_83_database():
    database_name = f"huginn_kan_83_upgrade_{uuid.uuid4().hex}"
    try:
        database_exists = _database_exists(database_name)
    except psycopg.Error as error:
        pytest.skip(
            "isolated upgrade test requires maintenance database access: "
            f"{type(error).__name__}"
        )
    if database_exists:
        raise RuntimeError(f"temporary database name already exists: {database_name}")

    try:
        maintenance_connection = psycopg.connect(
            _maintenance_database_url(), autocommit=True
        )
    except psycopg.Error as error:
        pytest.skip(
            "isolated upgrade test requires maintenance database access: "
            f"{type(error).__name__}"
        )

    try:
        with maintenance_connection as conn:
            assert conn.execute("SELECT current_database()").fetchone()[0] == "postgres"
            conn.execute(
                sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name))
            )
    except psycopg.errors.InsufficientPrivilege:
        pytest.skip("isolated upgrade test requires CREATE DATABASE permission")
    except BaseException:
        if _database_exists(database_name):
            _drop_temporary_database(database_name)
        raise

    try:
        configured_database_name = _configured_database_state()[0]
        connection_options = conninfo_to_dict(DATABASE_URL)
        connection_options["dbname"] = database_name
        database_url = make_conninfo(**connection_options)
        with psycopg.connect(database_url, autocommit=True) as conn:
            assert (
                conn.execute("SELECT current_database()").fetchone()[0] == database_name
            )
            for filename in _PRE_KAN_83_SCHEMA_FILES:
                schema_sql = (_SCHEMA_DIR / filename).read_text()
                if any(
                    line.lstrip().startswith("\\") for line in schema_sql.splitlines()
                ):
                    raise RuntimeError(
                        f"{filename} contains psql meta-commands and cannot run via psycopg"
                    )
                conn.execute(schema_sql)
        yield database_url, database_name, configured_database_name
    finally:
        _drop_temporary_database(database_name)
        assert _database_exists(database_name) is False


def test_temporary_database_skips_when_maintenance_connection_is_denied(monkeypatch):
    connect_calls = []
    drop_calls = []

    def deny_maintenance_connection(database_url, **options):
        connect_calls.append((database_url, options))
        raise psycopg.OperationalError("simulated maintenance authentication denial")

    def record_drop(database_name):
        drop_calls.append(database_name)

    monkeypatch.setattr(psycopg, "connect", deny_maintenance_connection)
    monkeypatch.setitem(globals(), "_drop_temporary_database", record_drop)

    with (
        pytest.raises(
            pytest.skip.Exception,
            match="maintenance database access",
        ),
        _temporary_pre_kan_83_database(),
    ):
        pytest.fail("maintenance denial should prevent the context body")

    assert len(connect_calls) == 1
    assert conninfo_to_dict(connect_calls[0][0])["dbname"] == "postgres"
    assert drop_calls == []


def test_temporary_database_skips_when_pre_create_connection_is_denied(monkeypatch):
    operations = []
    destructive_actions = []

    def database_does_not_exist(database_name):
        operations.append(("exists", database_name))
        return False

    def deny_pre_create_connection(database_url, **options):
        operations.append(
            ("connect", conninfo_to_dict(database_url)["dbname"], options)
        )
        raise psycopg.OperationalError("simulated pre-create connection denial")

    def record_drop(database_name):
        destructive_actions.append(("drop", database_name))

    monkeypatch.setitem(globals(), "_database_exists", database_does_not_exist)
    monkeypatch.setattr(psycopg, "connect", deny_pre_create_connection)
    monkeypatch.setitem(globals(), "_drop_temporary_database", record_drop)

    with (
        pytest.raises(
            pytest.skip.Exception,
            match="maintenance database access",
        ),
        _temporary_pre_kan_83_database(),
    ):
        pytest.fail("pre-create connection denial should prevent the context body")

    assert [operation[0] for operation in operations] == ["exists", "connect"]
    assert operations[1][1] == "postgres"
    assert destructive_actions == []


def test_temporary_database_is_dropped_when_post_create_setup_fails(monkeypatch):
    database_uuid = uuid.uuid4()
    database_name = f"huginn_kan_83_upgrade_{database_uuid.hex}"

    def fail_state_capture():
        raise RuntimeError("simulated configured-state capture failure")

    monkeypatch.setattr(uuid, "uuid4", lambda: database_uuid)
    monkeypatch.setitem(globals(), "_configured_database_state", fail_state_capture)

    try:
        with (
            pytest.raises(RuntimeError, match="configured-state capture failure"),
            _temporary_pre_kan_83_database(),
        ):
            pytest.fail("setup failure should prevent the context body")

        assert _database_exists(database_name) is False
    finally:
        if _database_exists(database_name):
            _drop_temporary_database(database_name)


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


def test_stale_success_cannot_clear_newer_retry_or_overwrite_newer_bronze_record():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    stable_id = f"task3-stale-success-{uuid.uuid4()}"
    url = f"https://www.eu-startups.com/directory/{stable_id}/"
    newer_lastmod = "2026-09-10T00:00:00+00:00"
    stale_lastmod = "2026-09-05T00:00:00+00:00"
    failure_proposed_watermark = "2026-09-09T23:59:59+00:00"
    stale_batch_proposed_watermark = "2026-09-20T00:00:00+00:00"
    previous_state = _isolate_eu_discovery_state([stable_id], [url])

    try:
        newer_record = _record(stable_id, newer_lastmod, html="<main>new</main>")
        repository.commit_batch(
            DiscoveryBatch((newer_record,), newer_lastmod, ()), str(uuid.uuid4())
        )
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("DELETE FROM bronze.eu_startups_discovery_state")
            conn.execute(
                "INSERT INTO bronze.eu_startups_discovery_state (singleton, watermark) "
                "VALUES (TRUE, %s)",
                ("2026-09-01T00:00:00+00:00",),
            )

        newer_failure = FailedListingOutcome(url, newer_lastmod, 503)
        repository.commit_batch(
            DiscoveryBatch((), failure_proposed_watermark, (newer_failure,)),
            str(uuid.uuid4()),
        )

        stale_record = _record(stable_id, stale_lastmod, html="<main>stale</main>")
        repository.commit_batch(
            DiscoveryBatch(
                (stale_record,),
                stale_batch_proposed_watermark,
                (),
            ),
            str(uuid.uuid4()),
        )

        with psycopg.connect(DATABASE_URL) as conn:
            stored = conn.execute(
                "SELECT payload FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            ).fetchone()

        assert stored == (newer_record.payload,)
        assert repository.list_retryable_listings() == (newer_failure,)
        assert repository.read_watermark() == stale_batch_proposed_watermark
    finally:
        _restore_eu_discovery_state([stable_id], [url], previous_state)


@pytest.mark.parametrize("status_code", [None, 503])
@pytest.mark.parametrize(
    "stale_lastmod",
    ["2026-09-05T00:00:00+00:00", "2026-09-10T00:00:00+00:00"],
)
def test_stale_failure_after_newer_success_leaves_durable_state_unchanged(
    status_code, stale_lastmod
):
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    stable_id = f"final-review-stale-failure-{uuid.uuid4()}"
    url = f"https://www.eu-startups.com/directory/{stable_id}/"
    successful_lastmod = "2026-09-10T00:00:00+00:00"
    record = _record(stable_id, successful_lastmod, html="<main>new</main>")
    previous_state = _isolate_eu_discovery_state([stable_id], [url])

    try:
        assert (
            repository.commit_batch(
                DiscoveryBatch((record,), successful_lastmod, ()), str(uuid.uuid4())
            )
            == 1
        )
        with psycopg.connect(DATABASE_URL) as conn:
            checkpoint_before = conn.execute(
                "SELECT watermark, updated_at, xmin "
                "FROM bronze.eu_startups_discovery_state WHERE singleton = TRUE"
            ).fetchone()

        assert checkpoint_before is not None

        assert (
            repository.commit_batch(
                DiscoveryBatch(
                    (),
                    stale_lastmod,
                    (_failure(stable_id, stale_lastmod, status_code),),
                ),
                str(uuid.uuid4()),
            )
            == 0
        )

        with psycopg.connect(DATABASE_URL) as conn:
            stored = conn.execute(
                "SELECT payload FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            ).fetchone()
            retry = conn.execute(
                "SELECT attempt_count, last_status_code, status "
                "FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (url,),
            ).fetchone()
            checkpoint_after = conn.execute(
                "SELECT watermark, updated_at, xmin "
                "FROM bronze.eu_startups_discovery_state WHERE singleton = TRUE"
            ).fetchone()

        assert stored == (record.payload,)
        assert retry is None
        assert checkpoint_after == checkpoint_before
        assert repository.list_retryable_listings() == ()
        assert repository.read_watermark() == successful_lastmod
    finally:
        _restore_eu_discovery_state([stable_id], [url], previous_state)


def test_stale_failure_and_later_success_commit_record_without_retry_and_advance():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    stale_target_id = f"stale-target-{uuid.uuid4()}"
    later_success_id = f"later-success-{uuid.uuid4()}"
    stale_url = f"https://www.eu-startups.com/directory/{stale_target_id}/"
    existing_lastmod = "2026-09-10T00:00:00+00:00"
    stale_lastmod = "2026-09-05T00:00:00+00:00"
    failure_pinned_proposal = "2026-09-04T23:59:59+00:00"
    later_success_lastmod = "2026-09-20T00:00:00+00:00"
    stable_ids = [stale_target_id, later_success_id]
    previous_state = _isolate_eu_discovery_state(stable_ids, [stale_url])

    try:
        existing_record = _record(
            stale_target_id, existing_lastmod, html="<main>existing</main>"
        )
        repository.commit_batch(
            DiscoveryBatch((existing_record,), existing_lastmod, ()),
            str(uuid.uuid4()),
        )
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute("DELETE FROM bronze.eu_startups_discovery_state")
            conn.execute(
                "INSERT INTO bronze.eu_startups_discovery_state "
                "(singleton, watermark) VALUES (TRUE, %s)",
                ("2026-09-01T00:00:00+00:00",),
            )

        later_record = _record(later_success_id, later_success_lastmod)
        written = repository.commit_batch(
            DiscoveryBatch(
                (later_record,),
                failure_pinned_proposal,
                (_failure(stale_target_id, stale_lastmod, 503),),
            ),
            str(uuid.uuid4()),
        )

        with psycopg.connect(DATABASE_URL) as conn:
            stored = dict(
                conn.execute(
                    "SELECT stable_id, payload FROM bronze.web_scrape_ingest "
                    "WHERE source = 'eu_startups' AND stable_id = ANY(%s)",
                    (stable_ids,),
                ).fetchall()
            )
            retry = conn.execute(
                "SELECT status FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (stale_url,),
            ).fetchone()

        assert written == 1
        assert stored == {
            stale_target_id: existing_record.payload,
            later_success_id: later_record.payload,
        }
        assert retry is None
        assert repository.list_retryable_listings() == ()
        assert repository.read_watermark() == later_success_lastmod
    finally:
        _restore_eu_discovery_state(stable_ids, [stale_url], previous_state)


def test_kan_83_additive_upgrade_isolated_from_configured_database_and_cleans_up():
    historical_id = f"pre-kan-83-{uuid.uuid4()}"
    discovery_id = f"final-review-upgrade-{uuid.uuid4()}"
    historical_run_id = str(uuid.uuid4())
    successful_lastmod = "2026-09-10T00:00:00+00:00"
    retry_lastmod = "2026-09-12T00:00:00+00:00"
    configured_database_state = _configured_database_state()

    with _temporary_pre_kan_83_database() as (
        database_url,
        database_name,
        configured_database_name,
    ):
        assert configured_database_name != database_name
        assert configured_database_name == configured_database_state[0]
        assert conninfo_to_dict(database_url)["dbname"] == database_name
        with psycopg.connect(database_url) as conn:
            assert (
                conn.execute(
                    "SELECT to_regclass('bronze.eu_startups_discovery_state')"
                ).fetchone()[0]
                is None
            )
            assert (
                conn.execute(
                    "SELECT to_regclass('bronze.eu_startups_listing_retry')"
                ).fetchone()[0]
                is None
            )
            conn.execute(
                "INSERT INTO bronze.web_scrape_ingest "
                "(source, stable_id, payload, content_hash, run_id) "
                "VALUES (%s, %s, '{\"historical\": true}'::jsonb, %s, %s::uuid)",
                ("pre_kan_83", historical_id, "pre-kan-83-hash", historical_run_id),
            )
            upgrade_sql = _KAN_83_UPGRADE.read_text()
            conn.execute(upgrade_sql)
            conn.execute(upgrade_sql)

            historical = conn.execute(
                "SELECT payload, content_hash, run_id FROM bronze.web_scrape_ingest "
                "WHERE source = 'pre_kan_83' AND stable_id = %s",
                (historical_id,),
            ).fetchone()

        assert historical == (
            {"historical": True},
            "pre-kan-83-hash",
            uuid.UUID(historical_run_id),
        )

        repository = PostgresEuStartupsDiscoveryRepository(database_url)
        record = _record(discovery_id, successful_lastmod)
        failure = _failure(discovery_id, retry_lastmod, 503)
        assert (
            repository.commit_batch(
                DiscoveryBatch((record,), retry_lastmod, (failure,)), str(uuid.uuid4())
            )
            == 1
        )
        assert repository.list_retryable_listings() == (failure,)
        assert repository.read_watermark() == retry_lastmod
        assert _configured_database_state() == configured_database_state

    assert _database_exists(database_name) is False
    assert _configured_database_state() == configured_database_state


def test_retry_count_is_persisted_while_network_and_5xx_remain_retryable():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    url_key = f"task2-retry-{uuid.uuid4()}"
    success_id = f"task2-later-success-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{url_key}/"
    lastmod = "2026-09-05T00:00:00+00:00"
    proposed = "2026-09-04T23:59:59+00:00"
    later_success_lastmod = "2026-09-06T00:00:00+00:00"
    previous_state = _isolate_eu_discovery_state([success_id], [failure_url])

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
        assert repository.list_retryable_listings() == (
            _failure(url_key, lastmod, 503),
        )

        repository.commit_batch(
            DiscoveryBatch(
                (_record(success_id, later_success_lastmod),),
                later_success_lastmod,
                (),
            ),
            str(uuid.uuid4()),
        )

        assert repository.read_watermark() == later_success_lastmod
    finally:
        _restore_eu_discovery_state([success_id], [failure_url], previous_state)


def test_overlapping_discovery_commits_keep_retryable_failure_and_advance_checkpoint(
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
    failure_proposed_watermark = datetime.fromisoformat(failure.lastmod) - timedelta(
        seconds=1
    )
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
                        DiscoveryBatch(
                            (), failure_proposed_watermark.isoformat(), (failure,)
                        ),
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

                    # The success waits for the retry transaction's advisory lock,
                    # then advances the checkpoint without discarding the retry.
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
        assert success_repository.read_watermark() == record.payload["lastmod"]
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


def test_persisted_retryable_failure_allows_later_success_and_is_listable():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    failure_key = f"task2-persisted-retry-{uuid.uuid4()}"
    failure_url = f"https://www.eu-startups.com/directory/{failure_key}/"
    success_id = f"task2-newer-success-{uuid.uuid4()}"
    failure_lastmod = "2026-09-03T00:00:00+00:00"
    failure_proposed_watermark = "2026-09-02T23:59:59+00:00"
    success_lastmod = "2026-09-06T00:00:00+00:00"
    previous_state = _isolate_eu_discovery_state([success_id], [failure_url])

    try:
        repository.commit_batch(
            DiscoveryBatch(
                (),
                failure_proposed_watermark,
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

        assert repository.read_watermark() == success_lastmod
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
        assert repository.read_watermark() == new_lastmod
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
        assert repository.read_watermark() == new_lastmod

        repository.commit_batch(
            DiscoveryBatch(
                (), old_lastmod, (_failure(url_key, old_lastmod, stale_status_code),)
            ),
            str(uuid.uuid4()),
        )
        assert read_retry() == newer_retry
        assert repository.read_watermark() == new_lastmod
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
        assert repository.read_watermark() == new_lastmod
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
