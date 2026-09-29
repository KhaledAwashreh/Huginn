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
from huginn.elt.ingestion.models import (
    DiscoveryBatch,
    FailedListingOutcome,
    RawRecord,
)
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter

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
    source = "eu_startups"

    def __init__(self, batch: DiscoveryBatch) -> None:
        self.batch = batch

    def fetch(self, _watermark, _retryable_listings) -> DiscoveryBatch:
        return self.batch


class CollectingJobRunWriter:
    def __init__(self) -> None:
        self.job_runs = []

    def write(self, job_run) -> None:
        self.job_runs.append(job_run)


class RecordingAdapter(StaticAdapter):
    def __init__(self, batch: DiscoveryBatch) -> None:
        super().__init__(batch)
        self.calls: list[tuple[str | None, tuple[FailedListingOutcome, ...]]] = []

    def fetch(
        self,
        watermark: str | None,
        retryable_listings: tuple[FailedListingOutcome, ...],
    ) -> DiscoveryBatch:
        self.calls.append((watermark, retryable_listings))
        return self.batch


def test_runner_does_not_advance_watermark_when_persistence_rolls_back():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    job_run_writer = CollectingJobRunWriter()
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
            EuStartupsDiscoveryRunner(
                StaticAdapter(batch), repository, job_run_writer
            ).run()

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


def test_runner_replays_retry_at_watermark_and_allows_later_progress():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    job_run_writer = CollectingJobRunWriter()
    retry_id = f"task3-retry-{uuid.uuid4()}"
    success_id = f"task3-success-{uuid.uuid4()}"
    retry_url = f"https://www.eu-startups.com/directory/{retry_id}/"
    retry_lastmod = "2026-09-05T00:00:00+00:00"
    success_lastmod = "2026-09-06T00:00:00+00:00"
    retry = FailedListingOutcome(retry_url, retry_lastmod, 503)
    previous_state = None

    try:
        with psycopg.connect(DATABASE_URL) as conn:
            previous_state = conn.execute(
                "SELECT watermark, updated_at "
                "FROM bronze.eu_startups_discovery_state WHERE singleton = TRUE"
            ).fetchone()
            conn.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (success_id,),
            )
            conn.execute(
                "DELETE FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (retry_url,),
            )
            conn.execute("DELETE FROM bronze.eu_startups_discovery_state")

        repository.commit_batch(
            DiscoveryBatch((), "2026-09-04T23:59:59+00:00", (retry,)),
            str(uuid.uuid4()),
        )
        success_batch = DiscoveryBatch(
            (
                RawRecord(
                    stable_id=success_id,
                    payload={
                        "url": f"https://www.eu-startups.com/directory/{success_id}/",
                        "html": "<main>later</main>",
                        "lastmod": success_lastmod,
                    },
                ),
            ),
            success_lastmod,
            (),
        )
        adapter = RecordingAdapter(success_batch)

        assert EuStartupsDiscoveryRunner(adapter, repository, job_run_writer).run() == 1

        assert adapter.calls == [(retry_lastmod, (retry,))]
        assert repository.read_watermark() == success_lastmod
        assert repository.list_retryable_listings() == (retry,)
    finally:
        with psycopg.connect(DATABASE_URL) as conn:
            conn.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (success_id,),
            )
            conn.execute(
                "DELETE FROM bronze.eu_startups_listing_retry WHERE url = %s",
                (retry_url,),
            )
            conn.execute("DELETE FROM bronze.eu_startups_discovery_state")
            if previous_state is not None:
                conn.execute(
                    "INSERT INTO bronze.eu_startups_discovery_state "
                    "(singleton, watermark, updated_at) VALUES (TRUE, %s, %s)",
                    previous_state,
                )


def test_runner_commits_bronze_rows_with_its_real_job_run_id():
    repository = PostgresEuStartupsDiscoveryRepository(DATABASE_URL)
    stable_id = f"task3-job-run-{uuid.uuid4()}"
    listing_url = f"https://www.eu-startups.com/directory/{stable_id}/"
    batch = DiscoveryBatch(
        records=(
            RawRecord(
                stable_id=stable_id,
                payload={
                    "url": listing_url,
                    "html": "<main>job run identity</main>",
                    "lastmod": "2026-09-06T00:00:00+00:00",
                },
            ),
        ),
        proposed_watermark="2026-09-06T00:00:00+00:00",
        failed_listings=(),
    )
    run_id = None

    try:
        assert (
            EuStartupsDiscoveryRunner(
                StaticAdapter(batch),
                repository,
                PostgresJobRunWriter(DATABASE_URL),
            ).run()
            == 1
        )

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT run_id::text FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            )
            (run_id,) = cur.fetchone()
            cur.execute(
                "SELECT source, status, rows_written, error "
                "FROM ops.job_runs WHERE id = %s::uuid",
                (run_id,),
            )
            job_run = cur.fetchone()

        assert job_run == ("eu_startups", "succeeded", 1, None)
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM bronze.web_scrape_ingest "
                "WHERE source = 'eu_startups' AND stable_id = %s",
                (stable_id,),
            )
            if run_id is not None:
                cur.execute("DELETE FROM ops.job_runs WHERE id = %s::uuid", (run_id,))
