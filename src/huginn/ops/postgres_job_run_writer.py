"""Postgres-backed JobRunWriterPort for ops.job_runs. See architecture
document sections 3 and 5, and adr/0005-logging-required-from-day-one.md.

Written to unblock a live end-to-end verification run: IngestionService
cannot actually run without a JobRunWriterPort implementation, and none
existed yet (huginn.ops.job_runs's own docstring flagged this as KAN-28's
gap, but KAN-28 only wired the calls, per its own ticket scope). Tracked
as its own ticket, Jira KAN-45.
"""

from __future__ import annotations

import logging

import psycopg

from huginn.ops.job_runs import JobRun

logger = logging.getLogger(__name__)

_UPSERT_SQL = """
    INSERT INTO ops.job_runs (id, source, started_at, finished_at, status, rows_written, error)
    VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE
    SET finished_at = EXCLUDED.finished_at,
        status = EXCLUDED.status,
        rows_written = EXCLUDED.rows_written,
        error = EXCLUDED.error
"""


class PostgresJobRunWriter:
    """`JobRunWriterPort` implementation against `ops.job_runs`.

    `IngestionService` calls `write()` twice per source per run: once at
    `RUNNING` (so a crashed run is visible, not silently absent), once at
    a terminal `succeeded`/`failed` state. `ops.job_runs.id` is the primary
    key, so this is an upsert keyed on `id`: the first call inserts, the
    second updates the same row in place rather than duplicating it.
    """

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    def write(self, job_run: JobRun) -> None:
        with psycopg.connect(self._database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    _UPSERT_SQL,
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
