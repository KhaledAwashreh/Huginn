"""Job-run metadata: `ops.job_runs`. See architecture document sections 3
and 5, which name cron plus a `job_runs` table as the orchestration
mechanism, and Jira KAN-27.

This module is the data model and writer contract only. Wiring
`IngestionService` to actually call `start_job_run`/`finish_job_run` and
write a row per source per run is Jira KAN-28's job, not this one's; no
concrete `JobRunWriterPort` implementation exists yet either, same as
`RawStorePort`/`StatePort` in `huginn.ingestion.ports`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol


class JobRunStatus:
    """The lifecycle states of a `job_runs` row. See architecture document
    sections 3 and 5.
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class JobRun:
    """One row of `ops.job_runs`: a single source's ingestion run.

    `id` doubles as the run ID already threaded through
    `RawStorePort.write` and `bronze.*.run_id` (architecture document
    section 4.1); this module does not mint a separate identifier for it.
    """

    id: str
    source: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    rows_written: int
    error: str | None


def start_job_run(source: str) -> JobRun:
    """Begin a run for `source`: a fresh ID, `RUNNING` status, `started_at`
    set to now. See architecture document section 5.
    """
    return JobRun(
        id=str(uuid.uuid4()),
        source=source,
        started_at=datetime.now(timezone.utc),
        finished_at=None,
        status=JobRunStatus.RUNNING,
        rows_written=0,
        error=None,
    )


def finish_job_run(
    job_run: JobRun,
    status: str,
    rows_written: int = 0,
    error: str | None = None,
) -> JobRun:
    """Close out `job_run` with a terminal `status`, returning a new
    `JobRun` rather than mutating the one passed in (same pattern as
    `apply_company_update` in `huginn.gold.dimensional`).
    """
    return replace(
        job_run,
        status=status,
        finished_at=datetime.now(timezone.utc),
        rows_written=rows_written,
        error=error,
    )


class JobRunWriterPort(Protocol):
    """Writes a `JobRun` to `ops.job_runs`. See architecture document
    sections 3 and 5. No concrete Postgres implementation exists yet
    (Jira KAN-28), matching `RawStorePort`/`StatePort` in
    `huginn.ingestion.ports`.
    """

    def write(self, job_run: JobRun) -> None:
        """Persist `job_run`'s current state as a row (or row update) in
        `ops.job_runs`.
        """
        ...
