"""Dedicated transactional runner for EU-Startups sitemap discovery."""

from __future__ import annotations

import logging

from huginn.elt.bronze.ports import EuStartupsDiscoveryRepositoryPort
from huginn.elt.ingestion.adapters.eu_startups import EuStartupsDiscoveryAdapter
from huginn.ops.job_runs import (
    JobRun,
    JobRunStatus,
    JobRunWriterPort,
    finish_job_run,
    start_job_run,
)

logger = logging.getLogger(__name__)


class EuStartupsDiscoveryRunner:
    """Coordinate EU discovery without changing ``IngestionService``.

    The source-specific repository owns every durable state transition, so a
    failed commit leaves its watermark and retry list unchanged.
    """

    def __init__(
        self,
        adapter: EuStartupsDiscoveryAdapter,
        repository: EuStartupsDiscoveryRepositoryPort,
        job_run_writer: JobRunWriterPort,
        *,
        allow_initial_backfill: bool = False,
    ) -> None:
        self._adapter = adapter
        self._repository = repository
        self._job_run_writer = job_run_writer
        self._allow_initial_backfill = allow_initial_backfill

    def run(self) -> int:
        """Fetch a batch from durable state and atomically persist it."""
        job_run = start_job_run(self._adapter.source)
        self._safe_write_job_run(job_run)
        try:
            watermark = self._repository.read_watermark()
            if watermark is None and not self._allow_initial_backfill:
                raise RuntimeError(
                    "Initial EU-Startups discovery has no durable watermark; "
                    "rerun eu-startups-discovery with --allow-initial-backfill "
                    "to authorize the historical crawl"
                )
            retryable_listings = self._repository.list_retryable_listings()
            batch = self._adapter.fetch(watermark, retryable_listings)
            written = self._repository.commit_batch(batch, job_run.id)
        except Exception as exc:
            logger.exception("EU-Startups discovery failed")
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
            "EU-Startups discovery succeeded: %d written, %d failed",
            written,
            len(batch.failed_listings),
        )
        return written

    def _safe_write_job_run(self, job_run: JobRun) -> None:
        try:
            self._job_run_writer.write(job_run)
        except Exception:
            if getattr(self._job_run_writer, "strict_tracking", False):
                raise
            logger.exception(
                "EU-Startups discovery failed to persist job_run state "
                "(id=%s, status=%s)",
                job_run.id,
                job_run.status,
            )
