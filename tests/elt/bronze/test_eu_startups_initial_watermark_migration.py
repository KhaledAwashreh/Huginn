from datetime import UTC, datetime, timedelta
from pathlib import Path

import psycopg
import pytest

from huginn.elt.bronze.repositories.eu_startups_discovery_repository import (
    PostgresEuStartupsDiscoveryRepository,
)
from huginn.elt.ingestion.eu_startups_discovery_runner import EuStartupsDiscoveryRunner
from huginn.elt.ingestion.models import DiscoveryBatch
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter
from tests.postgres_harness import provisioned_postgres

MIGRATION = Path("db/schema/bronze-eu-startups-initial-watermark.sql")


def test_missing_watermark_is_seeded_once_without_changing_retry_records():
    with (
        provisioned_postgres("huginn_initial_watermark") as url,
        psycopg.connect(url) as conn,
    ):
        conn.execute(
            "INSERT INTO bronze.eu_startups_listing_retry(url,lastmod,attempt_count,terminal_attempt_count,status) VALUES ('https://example.test/retry',now(),2,0,'retryable')"
        )
        conn.commit()
        retries = conn.execute(
            "SELECT * FROM bronze.eu_startups_listing_retry"
        ).fetchall()
        conn.commit()
        earliest = datetime.now(UTC) - timedelta(days=365)
        conn.execute(MIGRATION.read_text())
        latest = datetime.now(UTC) - timedelta(days=365)
        row = conn.execute(
            "SELECT watermark,updated_at FROM bronze.eu_startups_discovery_state"
        ).fetchone()
        assert earliest <= row[0] <= latest
        conn.execute(MIGRATION.read_text())
        assert conn.execute(
            "SELECT watermark,updated_at FROM bronze.eu_startups_discovery_state"
        ).fetchall() == [row]
        assert (
            conn.execute("SELECT * FROM bronze.eu_startups_listing_retry").fetchall()
            == retries
        )


@pytest.mark.parametrize(
    "watermark", ["2020-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"]
)
def test_existing_watermark_and_timestamp_are_preserved(watermark):
    with (
        provisioned_postgres("huginn_preserved_watermark") as url,
        psycopg.connect(url) as conn,
    ):
        conn.execute(
            "INSERT INTO bronze.eu_startups_discovery_state(singleton,watermark,updated_at) VALUES (true,%s,'2020-01-01T00:00:00Z')",
            (watermark,),
        )
        conn.commit()
        original = conn.execute(
            "SELECT * FROM bronze.eu_startups_discovery_state"
        ).fetchall()
        conn.execute(MIGRATION.read_text())
        assert (
            conn.execute("SELECT * FROM bronze.eu_startups_discovery_state").fetchall()
            == original
        )


def test_seeded_watermark_allows_normal_discovery_without_historical_override():
    class NoNetworkAdapter:
        source = "eu_startups"

        def fetch(self, watermark, retries):
            assert watermark is not None
            assert retries == ()
            return DiscoveryBatch((), watermark, ())

    with provisioned_postgres("huginn_seeded_discovery") as url:
        with psycopg.connect(url) as conn:
            conn.execute(MIGRATION.read_text())
        runner = EuStartupsDiscoveryRunner(
            NoNetworkAdapter(),
            PostgresEuStartupsDiscoveryRepository(url),
            PostgresJobRunWriter(url),
        )
        assert runner.run() == 0
        with psycopg.connect(url) as conn:
            assert conn.execute(
                "SELECT status FROM ops.job_runs WHERE source='eu_startups'"
            ).fetchone() == ("succeeded",)
