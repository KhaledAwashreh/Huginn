"""Live-Postgres integration coverage for PostgresJobRunWriter.write().

Runs against the throwaway Postgres that tests/conftest.py provisions,
fails rather than skips when testcontainers or Docker is unavailable (tests/conftest.py explains why). No DB-free unit test
exists alongside this one: unlike PostgresApiIngestStore's hash-compare
decision, write() has no separable pure logic, it is a single parameterized
upsert with nothing to decide (CLAUDE.md code standard 4, "wherever
possible").
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import UTC, datetime

import psycopg

from huginn.ops.job_runs import JobRun, JobRunStatus
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter


def test_write_inserts_a_row_matching_the_job_run(
    integration_database_url: str,
):
    writer = PostgresJobRunWriter(integration_database_url)
    job_run = JobRun(
        id=str(uuid.uuid4()),
        source="postgres-job-run-writer-integration-test",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status=JobRunStatus.SUCCEEDED,
        rows_written=42,
        error=None,
    )

    try:
        writer.write(job_run)

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT source, status, rows_written, error FROM ops.job_runs WHERE id = %s",
                (job_run.id,),
            )
            row = cur.fetchone()

        assert row == (job_run.source, job_run.status, job_run.rows_written, None)
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ops.job_runs WHERE id = %s", (job_run.id,))


def test_write_stores_a_failed_run_with_its_error(
    integration_database_url: str,
):
    writer = PostgresJobRunWriter(integration_database_url)
    job_run = JobRun(
        id=str(uuid.uuid4()),
        source="postgres-job-run-writer-integration-test",
        started_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
        status=JobRunStatus.FAILED,
        rows_written=0,
        error="simulated failure",
    )

    try:
        writer.write(job_run)

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT status, error FROM ops.job_runs WHERE id = %s",
                (job_run.id,),
            )
            row = cur.fetchone()

        assert row == (JobRunStatus.FAILED, "simulated failure")
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ops.job_runs WHERE id = %s", (job_run.id,))


def test_write_called_twice_for_the_same_id_updates_in_place_not_duplicates(
    integration_database_url: str,
):
    """IngestionService writes RUNNING first, then a terminal state second,
    both for the same job_run.id. Must be one row, updated, not two."""
    writer = PostgresJobRunWriter(integration_database_url)
    run_id = str(uuid.uuid4())
    running = JobRun(
        id=run_id,
        source="postgres-job-run-writer-integration-test",
        started_at=datetime.now(UTC),
        finished_at=None,
        status=JobRunStatus.RUNNING,
        rows_written=0,
        error=None,
    )
    succeeded = replace(
        running,
        status=JobRunStatus.SUCCEEDED,
        finished_at=datetime.now(UTC),
        rows_written=7,
    )

    try:
        writer.write(running)
        writer.write(succeeded)

        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("SELECT count(*) FROM ops.job_runs WHERE id = %s", (run_id,))
            (row_count,) = cur.fetchone()
            cur.execute(
                "SELECT status, rows_written, finished_at IS NOT NULL FROM ops.job_runs WHERE id = %s",
                (run_id,),
            )
            status, rows_written, has_finished_at = cur.fetchone()

        assert row_count == 1
        assert status == JobRunStatus.SUCCEEDED
        assert rows_written == 7
        assert has_finished_at is True
    finally:
        with psycopg.connect(integration_database_url) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ops.job_runs WHERE id = %s", (run_id,))
