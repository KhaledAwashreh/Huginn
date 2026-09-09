from __future__ import annotations

import logging

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
    def __init__(self, written_count: int | None = None) -> None:
        self.writes: list[tuple[str, str, list[RawRecord], str]] = []
        self._written_count = written_count

    def write(self, source: str, mechanism: str, records: list[RawRecord], run_id: str) -> int:
        self.writes.append((source, mechanism, records, run_id))
        return self._written_count if self._written_count is not None else len(records)


class FakeJobRunWriter:
    def __init__(self) -> None:
        self.written = []

    def write(self, job_run) -> None:
        self.written.append(job_run)


class FakeFailingJobRunWriter:
    """Raises on every write() call, to prove a bookkeeping failure never
    aborts the source loop (a prior version let it)."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def write(self, job_run) -> None:
        raise self._exc


def test_run_once_writes_fetched_records_to_raw_store():
    records = [RawRecord(stable_id="1", payload={"id": 1})]
    source = FakeSource("hn", records)
    raw_store = FakeRawStore()
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], raw_store, job_run_writer)

    service.run_once()

    assert len(raw_store.writes) == 1
    written_source, written_mechanism, written_records, written_run_id = raw_store.writes[0]
    assert written_source == "hn"
    assert written_mechanism == "api"
    assert written_records == records
    assert written_run_id == job_run_writer.written[0].id


def test_run_once_writes_a_running_job_run_before_fetching():
    records = [RawRecord(stable_id="1", payload={"id": 1})]
    source = FakeSource("hn", records)
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], FakeRawStore(), job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 2
    running_write = job_run_writer.written[0]
    assert running_write.source == "hn"
    assert running_write.status == JobRunStatus.RUNNING
    assert running_write.finished_at is None


def test_run_once_writes_a_succeeded_job_run_for_a_successful_source():
    records = [RawRecord(stable_id="1", payload={"id": 1}), RawRecord(stable_id="2", payload={"id": 2})]
    source = FakeSource("hn", records)
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], FakeRawStore(), job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 2
    job_run = job_run_writer.written[-1]
    assert job_run.source == "hn"
    assert job_run.status == JobRunStatus.SUCCEEDED
    assert job_run.rows_written == 2
    assert job_run.error is None
    assert job_run.finished_at is not None


def test_run_once_records_rows_written_from_the_raw_store_return_value_not_fetched_count():
    records = [RawRecord(stable_id="1", payload={"id": 1}), RawRecord(stable_id="2", payload={"id": 2})]
    source = FakeSource("hn", records)
    raw_store = FakeRawStore(written_count=0)  # every record hash-matched and was skipped
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([source], raw_store, job_run_writer)

    service.run_once()

    job_run = job_run_writer.written[-1]
    assert job_run.status == JobRunStatus.SUCCEEDED
    assert job_run.rows_written == 0


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


def test_run_once_isolates_a_source_whose_job_run_writer_call_fails():
    """A transient bookkeeping-write failure must not abort the run: the
    prior implementation let a job_run_writer.write() exception propagate
    out of run_once() entirely, aborting every remaining source."""
    good_records = [RawRecord(stable_id="1", payload={"id": 1})]
    first_source = FakeSource("hn", good_records)
    second_source = FakeSource("yc", good_records)
    raw_store = FakeRawStore()
    job_run_writer = FakeFailingJobRunWriter(RuntimeError("db unavailable"))
    service = IngestionService([first_source, second_source], raw_store, job_run_writer)

    service.run_once()

    assert first_source.fetch_calls == 1
    assert second_source.fetch_calls == 1
    assert len(raw_store.writes) == 2


def test_run_once_records_a_failed_job_run_for_a_raising_fetch():
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    job_run_writer = FakeJobRunWriter()
    service = IngestionService([failing_source], FakeRawStore(), job_run_writer)

    service.run_once()

    assert len(job_run_writer.written) == 2
    job_run = job_run_writer.written[-1]
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

    assert len(job_run_writer.written) == 2
    job_run = job_run_writer.written[-1]
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

    assert len(job_run_writer.written) == 4
    terminal_statuses = {
        job_run.source: job_run.status
        for job_run in job_run_writer.written
        if job_run.finished_at is not None
    }
    assert terminal_statuses == {"yc": JobRunStatus.SUCCEEDED, "hn": JobRunStatus.FAILED}


def test_run_once_returns_the_failed_source_count():
    good_source = FakeSource("yc", [RawRecord(stable_id="1", payload={"id": 1})])
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    service = IngestionService([good_source, failing_source], FakeRawStore(), FakeJobRunWriter())

    failed_count = service.run_once()

    assert failed_count == 1


def test_run_once_returns_zero_when_every_source_succeeds():
    good_source = FakeSource("yc", [RawRecord(stable_id="1", payload={"id": 1})])
    service = IngestionService([good_source], FakeRawStore(), FakeJobRunWriter())

    failed_count = service.run_once()

    assert failed_count == 0


def test_run_once_logs_an_exception_for_a_failing_source(caplog):
    failing_source = FakeFailingSource("hn", RuntimeError("boom"))
    service = IngestionService([failing_source], FakeRawStore(), FakeJobRunWriter())

    with caplog.at_level(logging.ERROR, logger="huginn.ingestion.service"):
        service.run_once()

    assert any(
        record.levelname == "ERROR" and "hn" in record.message and record.exc_info is not None
        for record in caplog.records
    )


def test_run_once_logs_run_start_and_finish(caplog):
    good_source = FakeSource("yc", [RawRecord(stable_id="1", payload={"id": 1})])
    service = IngestionService([good_source], FakeRawStore(), FakeJobRunWriter())

    with caplog.at_level(logging.INFO, logger="huginn.ingestion.service"):
        service.run_once()

    messages = [record.message for record in caplog.records]
    assert any("starting for 1 source(s)" in message for message in messages)
    assert any("finished: 1 succeeded, 0 failed" in message for message in messages)
    assert any("succeeded, wrote 1 record(s)" in message for message in messages)
