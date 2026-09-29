from __future__ import annotations

import uuid

import pytest

from huginn.elt.ingestion.eu_startups_discovery_runner import (
    EuStartupsDiscoveryRunner,
)
from huginn.elt.ingestion.models import (
    DiscoveryBatch,
    FailedListingOutcome,
    RawRecord,
)
from huginn.ops.job_runs import JobRunStatus


class FakeRepository:
    def __init__(self) -> None:
        self.watermark = "2026-09-04T23:59:59+00:00"
        self.retryable = (
            FailedListingOutcome(
                url="https://www.eu-startups.com/directory/retry-me/",
                lastmod="2026-09-05T00:00:00+00:00",
                status_code=503,
            ),
        )
        self.committed: tuple[DiscoveryBatch, str] | None = None

    def read_watermark(self) -> str:
        return self.watermark

    def list_retryable_listings(self) -> tuple[FailedListingOutcome, ...]:
        return self.retryable

    def commit_batch(self, batch: DiscoveryBatch, run_id: str) -> int:
        self.committed = (batch, run_id)
        return len(batch.records)


class FakeAdapter:
    source = "eu_startups"

    def __init__(self, batch: DiscoveryBatch) -> None:
        self.batch = batch
        self.calls: list[tuple[str | None, tuple[FailedListingOutcome, ...]]] = []

    def fetch(
        self,
        watermark: str | None,
        retryable_listings: tuple[FailedListingOutcome, ...],
    ) -> DiscoveryBatch:
        self.calls.append((watermark, retryable_listings))
        return self.batch


class RecordingJobRunWriter:
    def __init__(self) -> None:
        self.job_runs = []

    def write(self, job_run) -> None:
        self.job_runs.append(job_run)


class FailingRepository(FakeRepository):
    def commit_batch(self, batch: DiscoveryBatch, run_id: str) -> int:
        self.committed = (batch, run_id)
        raise RuntimeError("simulated persistence failure")


class FailingJobRunWriter:
    def write(self, job_run) -> None:
        raise RuntimeError("simulated job-run write failure")


def test_runner_supplies_durable_state_and_commits_the_returned_batch():
    batch = DiscoveryBatch(
        records=(
            RawRecord(
                stable_id="fresh",
                payload={
                    "url": "https://www.eu-startups.com/directory/fresh/",
                    "html": "<main>fresh</main>",
                    "lastmod": "2026-09-06T00:00:00+00:00",
                },
            ),
        ),
        proposed_watermark="2026-09-06T00:00:00+00:00",
        failed_listings=(),
    )
    repository = FakeRepository()
    adapter = FakeAdapter(batch)
    job_run_writer = RecordingJobRunWriter()

    written = EuStartupsDiscoveryRunner(adapter, repository, job_run_writer).run()

    assert written == 1
    assert adapter.calls == [(repository.watermark, repository.retryable)]
    assert repository.committed == (batch, job_run_writer.job_runs[0].id)
    assert len(job_run_writer.job_runs) == 2
    running, succeeded = job_run_writer.job_runs
    assert running.id == succeeded.id
    assert running.source == "eu_startups"
    assert running.status == JobRunStatus.RUNNING
    assert succeeded.status == JobRunStatus.SUCCEEDED
    assert succeeded.rows_written == written
    assert succeeded.error is None
    uuid.UUID(running.id)


def test_runner_replays_a_durable_retry_at_or_before_the_watermark():
    repository = FakeRepository()
    repository.watermark = "2026-09-06T00:00:00+00:00"
    batch = DiscoveryBatch((), None, ())
    adapter = FakeAdapter(batch)
    job_run_writer = RecordingJobRunWriter()

    EuStartupsDiscoveryRunner(adapter, repository, job_run_writer).run()

    assert adapter.calls == [(repository.watermark, repository.retryable)]


def test_runner_records_and_reraises_a_persistence_failure():
    repository = FailingRepository()
    adapter = FakeAdapter(DiscoveryBatch((), None, ()))
    job_run_writer = RecordingJobRunWriter()

    with pytest.raises(RuntimeError, match="simulated persistence failure"):
        EuStartupsDiscoveryRunner(adapter, repository, job_run_writer).run()

    assert repository.committed is not None
    assert repository.committed[1] == job_run_writer.job_runs[0].id
    assert len(job_run_writer.job_runs) == 2
    running, failed = job_run_writer.job_runs
    assert running.id == failed.id
    assert failed.status == JobRunStatus.FAILED
    assert failed.rows_written == 0
    assert failed.error == "simulated persistence failure"


def test_runner_does_not_let_job_run_writes_mask_core_work_or_failures():
    successful_repository = FakeRepository()
    adapter = FakeAdapter(DiscoveryBatch((), None, ()))

    assert (
        EuStartupsDiscoveryRunner(
            adapter, successful_repository, FailingJobRunWriter()
        ).run()
        == 0
    )
    assert successful_repository.committed is not None

    with pytest.raises(RuntimeError, match="simulated persistence failure"):
        EuStartupsDiscoveryRunner(
            adapter, FailingRepository(), FailingJobRunWriter()
        ).run()
