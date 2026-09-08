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


class FakeFailingSource:
    def __init__(self, source: str, exc: Exception) -> None:
        self.source = source
        self.mechanism = "api"
        self._exc = exc

    def fetch(self):
        raise self._exc


class FakeFailingRawStore:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc
        self.writes = []

    def write(self, source, mechanism, records, run_id):
        raise self._exc


def test_run_once_isolates_a_failing_source_and_still_runs_the_next_one():
    good_records = [RawRecord(stable_id="1", payload={"id": 1})]
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    good_source = FakeSource("yc", good_records)
    raw_store = FakeRawStore()
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([failing_source, good_source], raw_store, job_run_writer)

    service.run_once()

    assert good_source.fetch_calls == 1
    assert len(raw_store.writes) == 1
    assert raw_store.writes[0][0] == "yc"


def test_run_once_records_a_failed_job_run_for_a_raising_fetch():
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([failing_source], FakeRawStore(), job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 1
    job_run = job_run_writer.written[0]
    assert job_run.source == "hn"
    assert job_run.status == JobRunStatus.FAILED
    assert job_run.rows_written == 0
    assert job_run.error == "boom"
    assert job_run.finished_at is not None


def test_run_once_records_a_failed_job_run_for_a_raising_raw_store_write():
    records = [RawRecord(stable_id="1", payload={"id": 1})]
    source = FakeSource("hn", records)
    raw_store = FakeFailingRawStore(RuntimeError("disk full"))
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], raw_store, job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 1
    job_run = job_run_writer.written[0]
    assert job_run.status == JobRunStatus.FAILED
    assert job_run.error == "disk full"


def test_run_once_does_not_abort_when_the_last_source_fails():
    good_records = [RawRecord(stable_id="1", payload={"id": 1})]
    good_source = FakeSource("yc", good_records)
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    raw_store = FakeRawStore()
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([good_source, failing_source], raw_store, job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 2
    statuses = {job_run.source: job_run.status for job_run in job_run_writer.written}
    assert statuses == {"yc": JobRunStatus.SUCCEEDED, "hn": JobRunStatus.FAILED}
