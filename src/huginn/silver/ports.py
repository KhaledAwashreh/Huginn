"""Port contracts for the Silver staging loaders, entity resolver, and
manual-review queue writer. See architecture document section 5's
ports-and-adapters pattern, already used at the ingestion/Bronze boundary
(`huginn.ingestion.ports.RawStorePort`/`StatePort`) and CLAUDE.md design
standard 6. `HnStagingLoader`, `YcStagingLoader`, `SignalResolver`, and
`ManualReviewQueuer` depend only on these Protocols, never on `psycopg`
directly; the concrete Postgres classes implementing them live alongside
their respective orchestrators.

One port per orchestrator, covering both the reads and the writes that
orchestrator makes, rather than a separate reader port and writer port.
An adapter owns its connection, so a split pair would mean two
connections and two transactions per call; merged, each orchestrator call
is one connection and one transaction, and its reads and writes share a
single consistent snapshot. This also matches the Bronze boundary, where
`ApiIngestRepositoryPort` already covers lookup and write together.

Every port here is a context manager, and deliberately so: the connection
scope belongs to the orchestrator's whole call, not to each individual
statement. An orchestrator wraps its batch in `with port:` and every
statement inside shares one connection and one transaction, so a run over
N records costs one connect rather than one per record and a mid-loop
failure leaves no partial batch behind. Every data method below is only
valid between `__enter__` and `__exit__`, and no `__exit__` may suppress
the block's exception: it returns None, never a truthy value.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from huginn.silver.hn_staging import HnPostingStaging
    from huginn.silver.yc_staging import YcListingStaging


class RepositoryScopePort(Protocol):
    """The connection scope every Silver port shares. Extended by the
    ports below rather than injected on its own.
    """

    def __enter__(self) -> RepositoryScopePort:
        """Acquire whatever the statements below need, and return the
        object those statements are then called on.
        """
        ...

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        """Release what `__enter__` acquired, committing the block's work
        on a clean exit and discarding it if the block raised.

        Must not suppress the exception: return None, never a truthy value.
        """
        ...


class BronzeReaderPort(RepositoryScopePort, Protocol):
    """Reads raw bronze.api_ingest payloads for one source. Extended by
    both staging ports rather than injected on its own, since the read
    side is identical regardless of source (architecture document section
    4.1: one shared api_ingest table, `source` column distinguishes rows).
    """

    def read(self, source: str) -> list[dict]: ...


class HnStagingRepositoryPort(BronzeReaderPort, Protocol):
    """Reads bronze.api_ingest and upserts silver.hn_postings."""

    def upsert(self, row: HnPostingStaging) -> None: ...


class YcStagingRepositoryPort(BronzeReaderPort, Protocol):
    """Reads bronze.api_ingest and upserts silver.yc_listings."""

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


class SignalResolutionRepositoryPort(RepositoryScopePort, Protocol):
    """Reads every row currently in the per-source staging tables and
    upserts silver.resolved_signals.
    """

    def read_hn_postings(self) -> list[StagedSignal]: ...

    def read_yc_listings(self) -> list[StagedSignal]: ...

    def upsert(self, record: ResolvedSignalRecord) -> None: ...


class ManualReviewRepositoryPort(RepositoryScopePort, Protocol):
    """Reads every silver.resolved_signals row not yet resolved to a real
    company (match_confidence = 'no_existing_match') and queues each one
    for manual review, if not already queued. See docs/entities.md's
    ManualReviewCandidate: a row already queued (pending, confirmed, or
    rejected) must be left untouched.
    """

    def read_unmatched(self) -> list[tuple[str, str]]:
        """Returns (resolved_signal_id, candidate_company_key) pairs."""
        ...

    def insert_if_new(
        self, resolved_signal_id: str, candidate_company_key: str, match_score: int
    ) -> bool:
        """Returns True if a new row was inserted, False if one already existed."""
        ...
