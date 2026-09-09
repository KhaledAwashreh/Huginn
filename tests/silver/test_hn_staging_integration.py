"""Live-Postgres integration coverage for HnStagingLoader.load().

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from huginn.silver.hn_staging import HnStagingLoader
from huginn.silver.hn_staging_repository import PostgresHnStagingRepository
from huginn.silver.postgres_bronze_reader import PostgresBronzeReader

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
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable",
)


def test_load_upserts_bronze_hn_comments_into_silver_hn_postings():
    stable_id = str(uuid.uuid4().int)[:10]
    run_id = str(uuid.uuid4())
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.api_ingest (source, stable_id, payload, content_hash, run_id)
            VALUES ('hn', %s, %s, 'test-hash', %s::uuid)
            """,
            (
                stable_id,
                psycopg.types.json.Jsonb(
                    {
                        "id": int(stable_id),
                        "type": "comment",
                        "time": 1757404800,
                        "text": "TestCo Integration | Backend | Remote<p>A test posting.",
                    }
                ),
                run_id,
            ),
        )

    try:
        loader = HnStagingLoader(
            PostgresBronzeReader(DATABASE_URL),
            PostgresHnStagingRepository(DATABASE_URL),
        )
        written = loader.load()

        assert written >= 1

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT company_name_raw, description FROM silver.hn_postings WHERE stable_id = %s",
                (stable_id,),
            )
            company_name_raw, description = cur.fetchone()

        assert company_name_raw == "TestCo Integration"
        assert description == "A test posting."

        # Second load: same bronze row, must upsert in place, not duplicate.
        loader.load()
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM silver.hn_postings WHERE stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone()[0] == 1
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.hn_postings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'hn' AND stable_id = %s",
                (stable_id,),
            )


def test_a_failure_mid_batch_rolls_back_every_row_in_that_batch():
    """The batch is one transaction, so a bronze row that fails must undo
    the rows already written alongside it.

    Guards PostgresHnStagingRepository.__exit__'s rollback branch, which
    unit tests cannot reach: a fake writer has no transaction to roll back,
    so only a real database can show that the good row's upsert did not
    survive the bad row's failure. Without the rollback this test finds one
    committed row instead of none.

    The failure has to be raised client-side, before anything reaches the
    server, or the test proves nothing: a server-side error aborts the
    transaction, and COMMIT on an aborted transaction succeeds by rolling
    back, so a broken `__exit__` that always commits would still leave zero
    rows. A payload with no `time` therefore fails inside
    `parse_hn_posting`, mid-loop, with the connection's transaction still
    healthy and the good row's insert pending inside it. If the parser is
    ever hardened to tolerate a missing `time`, this test needs a different
    client-side mid-loop failure, not a server-side one.
    """
    # Read order decides whether the good row is written before the bad one
    # fails, and PostgresBronzeReader's SELECT has no ORDER BY: Postgres
    # serves it from the UNIQUE (source, stable_id) index, so rows arrive in
    # bronze stable_id order. Two equal-length all-digit ids compare the same
    # under every collation, so sorting them here fixes the order; the '9'
    # prefix also puts both after the real 8-digit HN ids, so genuine rows
    # are written into the transaction ahead of the failure too. The
    # precondition below re-checks this rather than trusting it.
    good_stable_id, bad_stable_id = sorted(
        ("9" + str(uuid.uuid4().int)[:9], "9" + str(uuid.uuid4().int)[:9])
    )
    run_id = str(uuid.uuid4())

    good_payload = {
        "id": int(good_stable_id),
        "type": "comment",
        "time": 1757404800,
        "text": "RollbackTestCo | Backend | Remote<p>Written first.",
    }
    # Same shape minus `time`, so parse_hn_posting raises KeyError instead
    # of returning a row. Ordering is the point: this must be parsed after
    # the good row has already been upserted into the open transaction.
    bad_payload = {
        "id": int(bad_stable_id),
        "type": "comment",
        "text": "BadTestCo | Backend | Remote<p>Never written.",
    }

    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.api_ingest (source, stable_id, payload, content_hash, run_id)
            VALUES ('hn', %s, %s, 'test-hash', %s::uuid),
                   ('hn', %s, %s, 'test-hash', %s::uuid)
            """,
            (
                good_stable_id,
                psycopg.types.json.Jsonb(good_payload),
                run_id,
                bad_stable_id,
                psycopg.types.json.Jsonb(bad_payload),
                run_id,
            ),
        )

    try:
        loader = HnStagingLoader(
            PostgresBronzeReader(DATABASE_URL),
            PostgresHnStagingRepository(DATABASE_URL),
        )

        # Precondition, not the assertion under test: if the read ever came
        # back with the bad row first, nothing would have been written
        # before the failure and the rollback assertion below would pass
        # for the wrong reason. Fail loudly instead of silently passing.
        with PostgresBronzeReader(DATABASE_URL) as reader:
            read_ids = [str(payload.get("id")) for payload in reader.read("hn")]
        assert read_ids.index(str(good_payload["id"])) < read_ids.index(
            str(bad_payload["id"])
        ), (
            "bronze read order put the failing row first; this test needs the "
            "good row written before the failure to mean anything"
        )

        with pytest.raises(KeyError):
            loader.load()

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM silver.hn_postings WHERE stable_id = ANY(%s)",
                ([good_stable_id, bad_stable_id],),
            )
            (row_count,) = cur.fetchone()

        assert row_count == 0
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.hn_postings WHERE stable_id = ANY(%s)",
                ([good_stable_id, bad_stable_id],),
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'hn' AND stable_id = ANY(%s)",
                ([good_stable_id, bad_stable_id],),
            )
