"""Live-Postgres integration coverage for PostgresJobRunWriter.write().

Skipped automatically when HUGINN_DATABASE_URL is unset or unreachable,
matching tests/bronze/test_api_ingest_store_integration.py's pattern.
No DB-free unit test exists alongside this one: unlike
PostgresApiIngestStore's hash-compare decision, write() has no separable
pure logic, it is a single parameterized upsert with nothing to decide
(CLAUDE.md code standard 4, "wherever possible").
"""

from __future__ import annotations

import os
import uuid
from dataclasses import replace
from datetime import datetime, timezone

import psycopg
import pytest

from huginn.ops.job_runs import JobRun, JobRunStatus
from huginn.ops.postgres_job_run_writer import PostgresJobRunWriter

DATABASE_URL = os.environ.get("HUGINN_DATABASE_URL")


def _database_reachable() -> bool:
    if not DATABASE_URL:
        return False
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
        return True
    except psycopg.OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    not _database_reachable(),
    reason="HUGINN_DATABASE_URL not set or Postgres unreachable",
)


def test_write_inserts_a_row_matching_the_job_run():
    writer = PostgresJobRunWriter(DATABASE_URL)
    job_run = JobRun(
        id=str(uuid.uuid4()),
        source="postgres-job-run-writer-integration-test",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        status=JobRunStatus.SUCCEEDED,
        rows_written=42,
        error=None,
    )

    try:
        writer.write(job_run)

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT source, status, rows_written, error FROM ops.job_runs WHERE id = %s",
                (job_run.id,),
            )
            row = cur.fetchone()

        assert row == (job_run.source, job_run.status, job_run.rows_written, None)
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ops.job_runs WHERE id = %s", (job_run.id,))


def test_write_stores_a_failed_run_with_its_error():
    writer = PostgresJobRunWriter(DATABASE_URL)
    job_run = JobRun(
        id=str(uuid.uuid4()),
        source="postgres-job-run-writer-integration-test",
        started_at=datetime.now(timezone.utc),
        finished_at=datetime.now(timezone.utc),
        status=JobRunStatus.FAILED,
        rows_written=0,
        error="simulated failure",
    )

    try:
        writer.write(job_run)

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT status, error FROM ops.job_runs WHERE id = %s",
                (job_run.id,),
            )
            row = cur.fetchone()

        assert row == (JobRunStatus.FAILED, "simulated failure")
    finally:
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ops.job_runs WHERE id = %s", (job_run.id,))


def test_write_called_twice_for_the_same_id_updates_in_place_not_duplicates():
    """IngestionService writes RUNNING first, then a terminal state second,
    both for the same job_run.id. Must be one row, updated, not two."""
    writer = PostgresJobRunWriter(DATABASE_URL)
    run_id = str(uuid.uuid4())
    running = JobRun(
        id=run_id,
        source="postgres-job-run-writer-integration-test",
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        status=JobRunStatus.RUNNING,
        rows_written=0,
        error=None,
    )
    succeeded = replace(
        running,
        status=JobRunStatus.SUCCEEDED,
        finished_at=datetime.now(timezone.utc),
        rows_written=7,
    )

    try:
        writer.write(running)
        writer.write(succeeded)

        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
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
        with psycopg.connect(DATABASE_URL) as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM ops.job_runs WHERE id = %s", (run_id,))
