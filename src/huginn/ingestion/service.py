"""IngestionService: the logic that would otherwise be reimplemented per
adapter. See architecture document section 5.

Holds which sources to fetch, in what order, and when a run counts as
complete. Adapters own a single protocol each and no ingestion policy.
Orchestration itself (cron plus a `job_runs` table, Jira KAN-9) is not
this class's concern; something external calls `run_once` on a schedule.
Logging follows `adr/0005-logging-required-from-day-one.md`: one logger per
module, no handler configuration here, log at the run and per-source
boundaries.
"""

from __future__ import annotations

import logging

from huginn.ingestion.ports import RawStorePort, SourcePort
from huginn.ops.job_runs import JobRunStatus, JobRunWriterPort, finish_job_run, start_job_run

logger = logging.getLogger(__name__)


class IngestionService:
    def __init__(
        self,
        sources: list[SourcePort],
        raw_store: RawStorePort,
        job_run_writer: JobRunWriterPort,
    ) -> None:
        self._sources = sources
        self._raw_store = raw_store
        self._job_run_writer = job_run_writer

    def run_once(self) -> int:
        """Fetch every configured source once and write results to Bronze.

        One source's `fetch()` or `raw_store.write()` raising does not abort
        the run: the exception is caught, recorded on that source's
        `job_runs` row as `FAILED`, and the loop continues to the next
        source. A `job_run_writer.write()` failure is isolated the same
        way: it is logged, never allowed to propagate and abort the loop.
        Each source's `job_run.id` is threaded through as the `run_id`
        argument to `raw_store.write`, per `huginn.ops.job_runs`'s
        `JobRun` docstring: it doubles as the Bronze run ID rather than a
        separately minted one. See architecture document section 5 and
        `adr/0005-logging-required-from-day-one.md`.

        Returns the number of sources that failed, so a caller (the CLI
        entrypoint) can decide whether to exit non-zero.
        """
        logger.info("run_once starting for %d source(s)", len(self._sources))

        succeeded_count = 0
        failed_count = 0
        for source in self._sources:
            job_run = start_job_run(source.source)
            self._safe_write_job_run(job_run)
            try:
                records = source.fetch()
                written = self._raw_store.write(
                    source.source, source.mechanism, records, job_run.id
                )
            except Exception as exc:
                logger.exception("source %s: run failed", source.source)
                job_run = finish_job_run(job_run, JobRunStatus.FAILED, error=str(exc) or repr(exc))
                self._safe_write_job_run(job_run)
                failed_count += 1
                continue
            job_run = finish_job_run(job_run, JobRunStatus.SUCCEEDED, rows_written=written)
            self._safe_write_job_run(job_run)
            logger.info("source %s: succeeded, wrote %d record(s)", source.source, written)
            succeeded_count += 1

        logger.info(
            "run_once finished: %d succeeded, %d failed",
            succeeded_count,
            failed_count,
        )
        return failed_count

    def _safe_write_job_run(self, job_run) -> None:
        """Persist `job_run`'s current state, logging rather than raising on
        failure. A `job_run_writer` write is bookkeeping, not the source's
        own work: a transient DB error here must never abort the source
        loop the way a genuine `fetch()`/`raw_store.write()` failure does.
        """
        try:
            self._job_run_writer.write(job_run)
        except Exception:
            logger.exception(
                "source %s: failed to persist job_run state (id=%s, status=%s)",
                job_run.source,
                job_run.id,
                job_run.status,
            )
