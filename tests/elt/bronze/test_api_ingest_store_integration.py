"""Live-Postgres integration coverage for PostgresApiIngestStore.write().

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
See docs/superpowers/plans/2026-09-08-kan-32-raw-store-port.md Task 4 and
Global Constraint 8: the fake-cursor unit tests in test_api_ingest_store.py
cannot verify real SQL execution against bronze.api_ingest (column names,
the ON CONFLICT target, the ::uuid cast, JSONB round-tripping). This test
is that verification, gated on a real database actually being present.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from huginn.elt.bronze.api_ingest_store import PostgresApiIngestStore
from huginn.elt.bronze.repositories.api_ingest_repository import (
    PostgresApiIngestRepository,
)
from huginn.elt.ingestion.models import RawRecord

DATABASE_URL = os.environ.get("HUGINN_DATABASE_URL")


def _database_reachable() -> bool:
    if not DATABASE_URL:
        return False
    try:
        with (
            psycopg.connect(DATABASE_URL, connect_timeout=2) as conn,
            conn.cursor() as cur,
        ):
            cur.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(),
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable; see plan Task 4",
)


def test_write_then_write_again_with_same_payload_only_touches_last_checked_at():
    store = PostgresApiIngestStore(PostgresApiIngestRepository(DATABASE_URL))
    source = "kan32-integration-test"
    stable_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    payload = {"title": "Integration Test Posting"}
    record = [RawRecord(stable_id=stable_id, payload=payload)]

    try:
        store.write(source, "api", record, run_id)
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, fetched_at, last_checked_at FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            first_hash, first_fetched_at, first_last_checked_at = cur.fetchone()

        # Second write, same payload: hash matches, so this should only
        # touch last_checked_at (build_touch_query), not rewrite the row.
        store.write(source, "api", record, str(uuid.uuid4()))
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, fetched_at, last_checked_at FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            second_hash, second_fetched_at, second_last_checked_at = cur.fetchone()

        assert second_hash == first_hash
        assert second_fetched_at == first_fetched_at
        # Strict comparison: fetched_at and last_checked_at both default to
        # now() on insert, so they start out equal. A weak >= assertion here
        # would still pass even if the touch UPDATE never ran (wrong table,
        # wrong WHERE clause, zero rows matched). The two writes happen in
        # separate transactions, so their now() values differ at
        # microsecond resolution and a strict > is reliable, not flaky.
        assert second_last_checked_at > first_last_checked_at

        # Third write, different payload and a new run_id: hash differs,
        # so this should fire the ON CONFLICT ... DO UPDATE overwrite
        # branch (build_write_query), not the touch path.
        third_run_id = str(uuid.uuid4())
        new_payload = {"title": "Integration Test Posting", "status": "updated"}
        store.write(
            source,
            "api",
            [RawRecord(stable_id=stable_id, payload=new_payload)],
            third_run_id,
        )
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT content_hash, payload, run_id, fetched_at FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )
            third_hash, third_payload, third_stored_run_id, third_fetched_at = (
                cur.fetchone()
            )

        assert third_hash != second_hash
        assert third_payload == new_payload
        assert str(third_stored_run_id) == third_run_id
        assert third_fetched_at > second_fetched_at
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = %s AND stable_id = %s",
                (source, stable_id),
            )


def test_a_failure_mid_batch_rolls_back_every_row_in_that_batch():
    """The batch is one transaction, so a record that fails must undo the
    records already written alongside it.

    Guards PostgresApiIngestRepository.__exit__'s rollback branch, which
    unit tests cannot reach: a fake repository has no transaction to roll
    back, so only a real database can show that the first record's write
    did not survive the second record's failure. Without the rollback this
    test finds one committed row instead of none.
    """
    store = PostgresApiIngestStore(PostgresApiIngestRepository(DATABASE_URL))
    source = "kan32-integration-test"
    good_stable_id = str(uuid.uuid4())
    bad_stable_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())

    # The second payload hashes fine but has no JSONB representation, so it
    # fails inside the repository's write, mid-loop, after the first record
    # has already been written into the open transaction. That ordering is
    # the point: it is what makes a missing rollback observable.
    records = [
        RawRecord(stable_id=good_stable_id, payload={"title": "Written First"}),
        RawRecord(stable_id=bad_stable_id, payload={"title": {"not", "json"}}),
    ]

    try:
        with pytest.raises(TypeError):
            store.write(source, "api", records, run_id)

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = ANY(%s)",
                (source, [good_stable_id, bad_stable_id]),
            )
            (row_count,) = cur.fetchone()

        assert row_count == 0
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.api_ingest "
                "WHERE source = %s AND stable_id = ANY(%s)",
                (source, [good_stable_id, bad_stable_id]),
            )
