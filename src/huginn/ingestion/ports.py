"""Port contracts for ingestion. See architecture document section 5.

The core (`IngestionService`) depends only on these protocols. Adapters
implement `SourcePort` per source (HN, YC, and later sources). Outbound
concerns (writing to Bronze, tracking cursor/watermark state) are their
own ports so the core never depends on Postgres directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RawRecord:
    """One fetched record, prior to any Bronze-side hashing or storage.

    `stable_id` is the source-native identifier used for the
    `(source, stable_id)` uniqueness key at Bronze (see architecture
    document section 4.1). `payload` is the raw, unmodified data as
    fetched, stored as-is in Bronze's `payload` column.
    """

    stable_id: str
    payload: dict


class SourcePort(Protocol):
    """Implemented once per source. One adapter, one protocol, no ingestion policy."""

    source: str
    """Short source identifier stored in Bronze's `source` column, e.g. "hn" or "yc"."""

    mechanism: str
    """Which Bronze table this source's rows land in: "api", "web_scrape", or "newsletter"."""

    def fetch(self) -> list[RawRecord]:
        """Fetch current records from the source. No ingestion policy here:
        pagination, retry, and rate-limit handling belong to the adapter,
        but *what to do* with the results (dedup, scheduling) is the
        `IngestionService`'s job, not this method's.
        """
        ...


class RawStorePort(Protocol):
    """Writes fetched records to Bronze. See architecture document section 4.1
    for the mechanism-grouped table layout and the hash-based write behavior.
    """

    def write(self, source: str, mechanism: str, records: list[RawRecord], run_id: str) -> None:
        """Write records to the appropriate Bronze table. Implementations must
        apply the skip-on-hash-match behavior: a record whose content hash
        matches the last stored hash for its `(source, stable_id)` should not
        insert a new row, only bump `last_checked_at` on the existing one.
        A record whose hash differs overwrites the existing row in place
        (Bronze's `UNIQUE (source, stable_id)` constraint allows exactly one
        row per entity; no prior version is retained).
        """
        ...


class StatePort(Protocol):
    """Per-entity content-hash watermark, replacing a source-provided cursor.
    See architecture document section 4.1: neither HN's Firebase API nor
    YC's Algolia backend offers a reliable "give me only what changed" cursor.
    """

    def last_hash(self, source: str, stable_id: str) -> str | None:
        """The last stored content hash for this entity, or None if never seen."""
        ...
