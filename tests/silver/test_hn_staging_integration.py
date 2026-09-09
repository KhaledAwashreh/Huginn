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
