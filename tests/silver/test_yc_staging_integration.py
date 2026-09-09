"""Live-Postgres integration coverage for PostgresYcStagingLoader.load().

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable.
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from huginn.silver.postgres_bronze_reader import PostgresBronzeReader
from huginn.silver.yc_staging import YcStagingLoader
from huginn.silver.yc_staging_repository import PostgresYcStagingRepository

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


def test_load_upserts_bronze_yc_hits_into_silver_yc_listings():
    stable_id = str(uuid.uuid4().int)[:10]
    run_id = str(uuid.uuid4())
    with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO bronze.api_ingest (source, stable_id, payload, content_hash, run_id)
            VALUES ('yc', %s, %s, 'test-hash', %s::uuid)
            """,
            (
                stable_id,
                psycopg.types.json.Jsonb(
                    {
                        "id": int(stable_id),
                        "name": "IntegrationTestCo",
                        "slug": "integrationtestco",
                        "stage": "Early",
                        "website": "https://integrationtestco.example",
                        "isHiring": True,
                        "one_liner": "A test listing.",
                        "long_description": None,
                        "launched_at": 1700000000,
                    }
                ),
                run_id,
            ),
        )

    try:
        loader = YcStagingLoader(
            PostgresBronzeReader(DATABASE_URL),
            PostgresYcStagingRepository(DATABASE_URL),
        )
        written = loader.load()

        assert written >= 1

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT company_name_raw, description FROM silver.yc_listings WHERE stable_id = %s",
                (stable_id,),
            )
            company_name_raw, description = cur.fetchone()

        assert company_name_raw == "IntegrationTestCo"
        assert description == "A test listing."

        loader.load()
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM silver.yc_listings WHERE stable_id = %s",
                (stable_id,),
            )
            assert cur.fetchone()[0] == 1
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM silver.yc_listings WHERE stable_id = %s", (stable_id,)
            )
            cur.execute(
                "DELETE FROM bronze.api_ingest WHERE source = 'yc' AND stable_id = %s",
                (stable_id,),
            )
