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


class IngestionService:
    def __init__(self, sources: list[SourcePort], raw_store: RawStorePort) -> None:
        self._sources = sources
        self._raw_store = raw_store

    def run_once(self) -> None:
        """Fetch every configured source once and write results to Bronze.

        TODO: per-source error isolation (one source failing should not
        abort the others), and recording the run in a `job_runs` table
        (architecture document section 5) are not yet implemented.
        """
        run_id = str(uuid.uuid4())
        for source in self._sources:
            records = source.fetch()
            self._raw_store.write(source.source, source.mechanism, records, run_id)
