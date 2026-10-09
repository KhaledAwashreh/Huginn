"""Job-run metadata: `ops.job_runs`. See architecture document sections 3
and 5, which name cron plus a `job_runs` table as the orchestration
mechanism, and Jira KAN-27.

`source` names a pipeline unit, not only an ingestion source, per
adr/0014-pipeline-entry-point-and-stage-failure-policy.md: an ingestion
source (`"hn"`, `"yc"`) when `IngestionService` (Jira KAN-28) writes the
row, or a pipeline stage label (`"silver.hn_staging"`, `"gold.company"`,
and so on) when `src/huginn/elt/__main__.py`'s `run_stages` writes it. No
schema change accompanies this widened meaning: the column already held a
short, freeform string.

This module is the data model and writer contract. Both callers write a
row per unit per run through `PostgresJobRunWriter` (Jira KAN-45), the
concrete `JobRunWriterPort` implementation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol


class JobRunStatus:
    """The lifecycle states of a `job_runs` row. See architecture document
    sections 3 and 5.

    `SKIPPED` is distinct from `FAILED`: a stage that never ran because a
    dependency did not succeed is not itself a fault, per
    adr/0014-pipeline-entry-point-and-stage-failure-policy.md's
    dependency-aware skip-on-failure policy. `src/huginn/elt/__main__.py`
    is the only writer of `SKIPPED` today; `IngestionService` (Jira KAN-28)
    never produces it, since ingestion isolates per-source failures rather
    than modeling sources as a dependency chain.
    """

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


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
    invocation_id: str | None = None
    parent_job_run_id: str | None = None
    execution_kind: str | None = None


def start_job_run(
    source: str,
    *,
    invocation_id: str | None = None,
    parent_job_run_id: str | None = None,
    execution_kind: str | None = None,
) -> JobRun:
    """Begin a run for `source`: a fresh ID, `RUNNING` status, `started_at`
    set to now. See architecture document section 5.
    """
    return JobRun(
        id=str(uuid.uuid4()),
        source=source,
        started_at=datetime.now(UTC),
        finished_at=None,
        status=JobRunStatus.RUNNING,
        rows_written=0,
        error=None,
        invocation_id=invocation_id,
        parent_job_run_id=parent_job_run_id,
        execution_kind=execution_kind,
    )


def finish_job_run(
    job_run: JobRun,
    status: str,
    rows_written: int = 0,
    error: str | None = None,
) -> JobRun:
    """Close out `job_run` with a terminal `status`, returning a new
    `JobRun` rather than mutating the one passed in (same pattern as
    `apply_company_update` in `huginn.elt.gold.dimensional`).
    """
    return replace(
        job_run,
        status=status,
        finished_at=datetime.now(UTC),
        rows_written=rows_written,
        error=error,
    )


class JobRunWriterPort(Protocol):
    """Writes a `JobRun` to `ops.job_runs`. See architecture document
    sections 3 and 5. `PostgresJobRunWriter` (Jira KAN-45) is the concrete
    implementation: `write()` must be safe to call twice for the same
    `job_run.id` (once at `RUNNING`, once at a terminal state), upserting
    rather than only ever inserting.
    """

    def write(self, job_run: JobRun) -> None:
        """Persist `job_run`'s current state as a row (or row update) in
        `ops.job_runs`.
        """
        ...
