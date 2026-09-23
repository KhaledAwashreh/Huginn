from __future__ import annotations

from huginn.elt.ingestion.eu_startups_discovery_runner import (
    EuStartupsDiscoveryRunner,
)
from huginn.elt.ingestion.models import (
    DiscoveryBatch,
    FailedListingOutcome,
    RawRecord,
)


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

    written = EuStartupsDiscoveryRunner(adapter, repository).run(
        "11111111-1111-1111-1111-111111111111"
    )

    assert written == 1
    assert adapter.calls == [(repository.watermark, repository.retryable)]
    assert repository.committed == (batch, "11111111-1111-1111-1111-111111111111")
