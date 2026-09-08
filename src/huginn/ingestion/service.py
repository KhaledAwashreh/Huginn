"""IngestionService: the logic that would otherwise be reimplemented per
adapter. See architecture document section 5.

Holds which sources to fetch, in what order, and when a run counts as
complete. Adapters own a single protocol each and no ingestion policy.
Orchestration itself (cron plus a `job_runs` table, Jira KAN-9) is not
this class's concern; something external calls `run_once` on a schedule.
"""

from __future__ import annotations

import uuid

from huginn.ingestion.ports import RawStorePort, SourcePort
from huginn.ops.job_runs import JobRunStatus, JobRunWriterPort, finish_job_run, start_job_run


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

    def run_once(self) -> None:
        """Fetch every configured source once and write results to Bronze.

        See architecture document section 5. Each source gets its own
        `job_runs` row (`huginn.ops.job_runs`); this method does not yet
        isolate one source's failure from the next (Task 2).
        """
        run_id = str(uuid.uuid4())
        for source in self._sources:
            job_run = start_job_run(source.source)
            records = source.fetch()
            self._raw_store.write(source.source, source.mechanism, records, run_id)
            job_run = finish_job_run(job_run, JobRunStatus.SUCCEEDED, rows_written=len(records))
            self._job_run_writer.write(job_run)
