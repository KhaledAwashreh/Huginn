"""Ingestion data shapes. See architecture document section 5.

Separated from `ports.py` so the protocols file holds contracts only and
the data a contract passes around has its own home, consistent with the
`models.py` / `ports.py` / `repositories/` split every ELT stage uses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawRecord:
    """One fetched record, prior to any Bronze-side hashing or storage.

    `stable_id` is the source-native identifier used for the
    `(source, stable_id)` uniqueness key at Bronze (see architecture
    document section 4.1). `payload` is the source-provided data as fetched,
    subject only to documented adapter-level privacy filtering before it is
    stored in Bronze's `payload` column.
    """

    stable_id: str
    payload: dict


@dataclass(frozen=True)
class FailedListingOutcome:
    """One EU discovery detail-page fetch that did not produce a raw record.

    `status_code` distinguishes a confirmed HTTP failure (notably 404/410)
    from a transport or otherwise unclassified failure for retry policy.
    """

    url: str
    lastmod: str
    status_code: int | None


@dataclass(frozen=True)
class DiscoveryBatch:
    """The complete, not-yet-persisted outcome of one EU discovery pass."""

    records: tuple[RawRecord, ...]
    proposed_watermark: str | None
    failed_listings: tuple[FailedListingOutcome, ...]
