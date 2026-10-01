"""Dedicated EU-Startups enrichment runner and job-run boundary for KAN-83."""

from __future__ import annotations

import logging

from huginn.elt.bronze.ports import EuStartupsEnrichmentRepositoryPort
from huginn.elt.ingestion.adapters.eu_startups_enrichment import (
    EuStartupsEnrichmentAdapter,
)
from huginn.ops.job_runs import (
    JobRun,
    JobRunStatus,
    JobRunWriterPort,
    finish_job_run,
    start_job_run,
)

logger = logging.getLogger(__name__)


class EuStartupsEnrichmentRunner:
    """Coordinate candidate searches and atomic Bronze/Gold persistence."""

    def __init__(
        self,
        adapter: EuStartupsEnrichmentAdapter,
        repository: EuStartupsEnrichmentRepositoryPort,
        job_run_writer: JobRunWriterPort,
    ) -> None:
        self._adapter = adapter
        self._repository = repository
        self._job_run_writer = job_run_writer

    def run(self) -> int:
        """Fetch one bounded batch and record its atomic persistence result."""
        job_run = start_job_run(self._adapter.source)
        self._safe_write_job_run(job_run)
        try:
            batch = self._adapter.fetch_batch()
            written = self._repository.persist_batch(batch, job_run.id)
        except Exception as exc:
            logger.exception("EU-Startups enrichment failed")
            self._safe_write_job_run(
                finish_job_run(
                    job_run,
                    JobRunStatus.FAILED,
                    error=str(exc) or repr(exc),
                )
            )
            raise

        self._safe_write_job_run(
            finish_job_run(
                job_run,
                JobRunStatus.SUCCEEDED,
                rows_written=written,
            )
        )
        logger.info(
            "EU-Startups enrichment succeeded: %d written, %d definitive names",
            written,
            len(batch.definitive_names),
        )
        return written

    def _safe_write_job_run(self, job_run: JobRun) -> None:
        try:
            self._job_run_writer.write(job_run)
        except Exception:
            logger.exception(
                "EU-Startups enrichment failed to persist job_run state "
                "(id=%s, status=%s)",
                job_run.id,
                job_run.status,
            )
