"""Dependency-aware execution for the ELT pipeline's named stages."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from huginn.ops.job_runs import (
    JobRun,
    JobRunStatus,
    JobRunWriterPort,
    finish_job_run,
    start_job_run,
)
from huginn.pipeline_control.application.read_models.tracking_context import (
    TrackingContext,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Stage:
    """One pipeline unit and the stages that must succeed before it runs."""

    name: str
    run: Callable[[], int]
    depends_on: tuple[str, ...] = ()
    run_managed: Callable[[TrackingContext], int] | None = None


def _safe_write_job_run(job_run_writer: JobRunWriterPort, job_run: JobRun) -> None:
    """Treat job-run writes as bookkeeping; a write failure never aborts work."""
    try:
        job_run_writer.write(job_run)
    except Exception:
        logger.exception(
            "stage %s: failed to persist job_run state (id=%s, status=%s)",
            job_run.source,
            job_run.id,
            job_run.status,
        )


def run_stages(
    stages: list[Stage],
    job_run_writer: JobRunWriterPort,
    *,
    invocation_id: UUID | None = None,
    strict_tracking: bool = False,
) -> dict[str, str]:
    """Run stages in order and record SUCCEEDED, FAILED, or SKIPPED per stage.

    A stage whose dependencies did not succeed is recorded as SKIPPED. A
    raised stage error is recorded as FAILED and does not stop unrelated
    stages from getting their chance to run.
    """

    def persist(job_run: JobRun) -> None:
        if strict_tracking:
            job_run_writer.write(job_run)
        else:
            _safe_write_job_run(job_run_writer, job_run)

    def start(name: str) -> JobRun:
        return start_job_run(
            name,
            invocation_id=str(invocation_id) if invocation_id else None,
            execution_kind="stage" if invocation_id else None,
        )

    statuses: dict[str, str] = {}
    for stage in stages:
        unmet_dependencies = [
            dependency
            for dependency in stage.depends_on
            if statuses.get(dependency) != JobRunStatus.SUCCEEDED
        ]
        if unmet_dependencies:
            logger.warning(
                "stage %s: skipped, dependency not succeeded: %s",
                stage.name,
                ", ".join(unmet_dependencies),
            )
            job_run = start(stage.name)
            job_run = finish_job_run(
                job_run,
                JobRunStatus.SKIPPED,
                error=f"dependency not succeeded: {', '.join(unmet_dependencies)}",
            )
            persist(job_run)
            statuses[stage.name] = JobRunStatus.SKIPPED
            continue

        job_run = start(stage.name)
        persist(job_run)
        started_at = time.monotonic()
        try:
            if invocation_id is not None and stage.run_managed is not None:
                rows_written = stage.run_managed(
                    TrackingContext(invocation_id, UUID(job_run.id), stage.name)
                )
            else:
                rows_written = stage.run()
        except Exception as exc:
            from huginn.pipeline_control.application.errors.execution import (
                TrackingUncertainError,
            )

            if isinstance(exc, TrackingUncertainError):
                raise
            elapsed_seconds = time.monotonic() - started_at
            logger.exception(
                "stage %s: failed after %.1fs", stage.name, elapsed_seconds
            )
            job_run = finish_job_run(
                job_run, JobRunStatus.FAILED, error=str(exc) or repr(exc)
            )
            persist(job_run)
            statuses[stage.name] = JobRunStatus.FAILED
            continue

        elapsed_seconds = time.monotonic() - started_at
        logger.info(
            "stage %s: succeeded in %.1fs, %d row(s)",
            stage.name,
            elapsed_seconds,
            rows_written,
        )
        job_run = finish_job_run(
            job_run, JobRunStatus.SUCCEEDED, rows_written=rows_written
        )
        persist(job_run)
        statuses[stage.name] = JobRunStatus.SUCCEEDED

    return statuses
