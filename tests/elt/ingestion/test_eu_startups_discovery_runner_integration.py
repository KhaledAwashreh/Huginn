from __future__ import annotations

import os
import uuid

import psycopg
import pytest

from huginn.elt.bronze.repositories.eu_startups_discovery_repository import (
    PostgresEuStartupsDiscoveryRepository,
)
from huginn.elt.ingestion.eu_startups_discovery_runner import (
    EuStartupsDiscoveryRunner,
)
from huginn.elt.ingestion.models import DiscoveryBatch, RawRecord

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


class StaticAdapter:
    def __init__(self, batch: DiscoveryBatch) -> None:
        self.batch = batch

    def fetch(self, _watermark, _retryable_listings) -> DiscoveryBatch:
        return self.batch


def test_runner_does_not_advance_watermark_when_persistence_rolls_back():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    baseline = "2026-09-01T00:00:00+00:00"
    stable_id = f"task3-rollback-{uuid.uuid4()}"
    previous_state = None

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            previous_state = conn.execute(
                "SELECT watermark, updated_at "
                "FROM bronze.eu_startups_discovery_state WHERE singleton = TRUE"
            ).fetchone()
            conn.execute("DELETE FROM bronze.eu_startups_discovery_state")
            conn.execute(
                "INSERT INTO bronze.eu_startups_discovery_state (singleton, watermark) "
                "VALUES (TRUE, %s)",
                (baseline,),
            )
            conn.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            )

        batch = DiscoveryBatch(
            records=(
                RawRecord(
                    stable_id=stable_id,
                    payload={
                        "url": f"https://www.eu-startups.com/directory/{stable_id}/",
                        "html": {"not", "json-serializable"},
                        "lastmod": "2026-09-06T00:00:00+00:00",
                    },
                ),
            ),
            proposed_watermark="2026-09-06T00:00:00+00:00",
            failed_listings=(),
        )

        with pytest.raises(TypeError):
            EuStartupsDiscoveryRunner(StaticAdapter(batch), repository).run(
                str(uuid.uuid4())
            )

        assert repository.read_watermark() == baseline
    finally:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            )
            conn.execute("DELETE FROM bronze.eu_startups_discovery_state")
            if previous_state is not None:
                conn.execute(
                    "INSERT INTO bronze.eu_startups_discovery_state "
                    "(singleton, watermark, updated_at) VALUES (TRUE, %s, %s)",
                    previous_state,
                )
