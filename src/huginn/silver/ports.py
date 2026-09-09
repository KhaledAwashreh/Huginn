"""Port contracts for the Silver staging loaders, entity resolver, and
manual-review queue writer. See architecture document section 5's
ports-and-adapters pattern, already used at the ingestion/Bronze boundary
(`huginn.ingestion.ports.RawStorePort`/`StatePort`) and CLAUDE.md design
standard 6. `HnStagingLoader`, `YcStagingLoader`, `SignalResolver`, and
`ManualReviewQueuer` depend only on these Protocols, never on `psycopg`
directly; the concrete Postgres classes implementing them live alongside
their respective orchestrators.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from huginn.silver.hn_staging import HnPostingStaging
    from huginn.silver.yc_staging import YcListingStaging


class BronzeReaderPort(Protocol):
    """Reads raw bronze.api_ingest payloads for one source. Shared by
    every staging loader, since the read side is identical regardless of
    source (architecture document section 4.1: one shared api_ingest
    table, `source` column distinguishes rows).
    """

    def read(self, source: str) -> list[dict]: ...


class HnStagingWriterPort(Protocol):
    """Upserts one row into silver.hn_postings."""

    def upsert(self, row: HnPostingStaging) -> None: ...


class YcStagingWriterPort(Protocol):
    """Upserts one row into silver.yc_listings."""

    def upsert(self, row: YcListingStaging) -> None: ...


@dataclass(frozen=True)
class StagedSignal:
    """One row read back from either per-source staging table, tagged
    with its source so `SignalResolver` can build a placeholder key
    without the reader needing to know about resolution at all.
    """

    source: str
    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str


class SilverStagingReaderPort(Protocol):
    """Reads every row currently in the per-source staging tables."""

    def read_hn_postings(self) -> list[StagedSignal]: ...

    def read_yc_listings(self) -> list[StagedSignal]: ...


@dataclass(frozen=True)
class ResolvedSignalRecord:
    """One row to upsert into silver.resolved_signals, produced by
    `resolve_signal` from a `StagedSignal`.
    """

    source: str
    source_stable_id: str
    resolved_company_key: str
    company_name_raw: str
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str
    match_confidence: str


class ResolvedSignalWriterPort(Protocol):
    """Upserts one row into silver.resolved_signals."""

    def upsert(self, record: ResolvedSignalRecord) -> None: ...


class UnmatchedSignalReaderPort(Protocol):
    """Reads every silver.resolved_signals row not yet resolved to a
    real company (match_confidence = 'no_existing_match').
    """

    def read_unmatched(self) -> list[tuple[str, str]]:
        """Returns (resolved_signal_id, candidate_company_key) pairs."""
        ...


class ManualReviewQueueWriterPort(Protocol):
    """Queues one unmatched signal for manual review, if not already
    queued. See docs/entities.md's ManualReviewCandidate: a row already
    queued (pending, confirmed, or rejected) must be left untouched.
    """

    def insert_if_new(
        self, resolved_signal_id: str, candidate_company_key: str, match_score: int
    ) -> bool:
        """Returns True if a new row was inserted, False if one already existed."""
        ...
