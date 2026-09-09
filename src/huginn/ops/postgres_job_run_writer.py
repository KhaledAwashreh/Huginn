"""Postgres-backed JobRunWriterPort for ops.job_runs. See architecture
document sections 3 and 5, and adr/0005-logging-required-from-day-one.md.

Written to unblock a live end-to-end verification run: IngestionService
cannot actually run without a JobRunWriterPort implementation, and none
existed yet (huginn.ops.job_runs's own docstring flagged this as KAN-28's
gap, but KAN-28 only wired the calls, per its own ticket scope). Not
tracked under its own Jira ticket; fold into KAN-31 or file separately.
"""

from __future__ import annotations

import logging

import psycopg

from huginn.ops.job_runs import JobRun

logger = logging.getLogger(__name__)

_INSERT_SQL = """
    INSERT INTO ops.job_runs (id, source, started_at, finished_at, status, rows_written, error)
    VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)
"""


class PostgresJobRunWriter:
    """`JobRunWriterPort` implementation against `ops.job_runs`.

    `IngestionService` calls `write()` exactly once per source per run,
    with `job_run` already in its terminal (`succeeded`/`failed`) state
    (see `huginn.ingestion.service.IngestionService.run_once`), so this is
    a single INSERT, never an UPDATE.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def write(self, job_run: JobRun) -> None:
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _INSERT_SQL,
                    (
                        job_run.id,
                        job_run.source,
                        job_run.started_at,
                        job_run.finished_at,
                        job_run.status,
                        job_run.rows_written,
                        job_run.error,
                    ),
                )
        logger.info(
            "ops.job_runs write id=%s source=%s status=%s rows_written=%d",
            job_run.id,
            job_run.source,
            job_run.status,
            job_run.rows_written,
        )
