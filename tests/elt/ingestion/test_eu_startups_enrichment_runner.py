import pytest

from huginn.elt.ingestion.eu_startups_enrichment_runner import (
    EuStartupsEnrichmentRunner,
)
from huginn.elt.ingestion.models import (
    EnrichmentBatch,
    EnrichmentCandidateOutcome,
    EnrichmentOutcomeStatus,
    RawRecord,
)
from huginn.ops.job_runs import JobRunStatus


class _Adapter:
    source = "eu_startups"

    def __init__(self, batch):
        self.batch = batch
        self.called = False

    def fetch_batch(self):
        self.called = True
        return self.batch


class _Repository:
    def __init__(self, error=None):
        self.error = error
        self.persisted = None

    def persist_batch(self, batch, run_id):
        self.persisted = (batch, run_id)
        if self.error:
            raise self.error
        return len(batch.records)


class _JobRunWriter:
    def __init__(self):
        self.job_runs = []

    def write(self, job_run):
        self.job_runs.append(job_run)


def _batch():
    return EnrichmentBatch(
        records=(
            RawRecord(
                "brightroom",
                {
                    "url": "https://www.eu-startups.com/directory/brightroom/",
                    "html": "<main />",
                    "lastmod": "2026-09-30T10:00:00+00:00",
                },
            ),
        ),
        outcomes=(
            EnrichmentCandidateOutcome("Brightroom", EnrichmentOutcomeStatus.ENRICHED),
        ),
    )


def test_runner_persists_batch_and_marks_job_run_succeeded():
    adapter = _Adapter(_batch())
    repository = _Repository()
    writer = _JobRunWriter()

    result = EuStartupsEnrichmentRunner(adapter, repository, writer).run()

    assert result == 1
    assert adapter.called
    assert repository.persisted[0] is adapter.batch
    assert repository.persisted[1] == writer.job_runs[0].id
    assert [run.status for run in writer.job_runs] == [
        JobRunStatus.RUNNING,
        JobRunStatus.SUCCEEDED,
    ]
    assert writer.job_runs[-1].rows_written == 1


def test_runner_marks_job_run_failed_and_reraises_persistence_error():
    adapter = _Adapter(_batch())
    repository = _Repository(RuntimeError("database unavailable"))
    writer = _JobRunWriter()

    with pytest.raises(RuntimeError, match="database unavailable"):
        EuStartupsEnrichmentRunner(adapter, repository, writer).run()

    assert [run.status for run in writer.job_runs] == [
        JobRunStatus.RUNNING,
        JobRunStatus.FAILED,
    ]
    assert writer.job_runs[-1].error == "database unavailable"
