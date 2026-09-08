from __future__ import annotations

from huginn.ingestion.ports import RawRecord
from huginn.ingestion.service import IngestionService
from huginn.ops.job_runs import JobRunStatus


class FakeSource:
    def __init__(self, source: str, records: list[RawRecord]) -> None:
        self.source = source
        self.mechanism = "api"
        self._records = records
        self.fetch_calls = 0

    def fetch(self) -> list[RawRecord]:
        self.fetch_calls += 1
        return self._records


class FakeRawStore:
    def __init__(self) -> None:
        self.writes: list[tuple[str, str, list[RawRecord], str]] = []

    def write(self, source: str, mechanism: str, records: list[RawRecord], run_id: str) -> None:
        self.writes.append((source, mechanism, records, run_id))


class FakeJobRunWriter:
    def __init__(self) -> None:
        self.written = []

    def write(self, job_run) -> None:
        self.written.append(job_run)


def test_run_once_writes_fetched_records_to_raw_store():
    records = [RawRecord(stable_id="1", payload={"id": 1})]
    source = FakeSource("hn", records)
    raw_store = FakeRawStore()
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], raw_store, job_run_writer)

    service.run_once()

    assert len(raw_store.writes) == 1
    written_source, written_mechanism, written_records, _run_id = raw_store.writes[0]
    assert written_source == "hn"
    assert written_mechanism == "api"
    assert written_records == records


def test_run_once_writes_a_succeeded_job_run_for_a_successful_source():
    records = [RawRecord(stable_id="1", payload={"id": 1}), RawRecord(stable_id="2", payload={"id": 2})]
    source = FakeSource("hn", records)
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], FakeRawStore(), job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 1
    job_run = job_run_writer.written[0]
    assert job_run.source == "hn"
    assert job_run.status == JobRunStatus.SUCCEEDED
    assert job_run.rows_written == 2
    assert job_run.error is None
    assert job_run.finished_at is not None
