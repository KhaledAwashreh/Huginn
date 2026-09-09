"""Silver data shapes. See architecture document section 5.

Separated from `ports.py` so the protocols file holds contracts only and
the data a contract passes around has its own home, matching the
`models.py` / `ports.py` / `repositories/` shape Silver's own package
now uses throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class HnPostingStaging:
    """One row of silver.hn_postings. See docs/entities.md's HnPostingStaging."""

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str


@dataclass(frozen=True)
class YcListingStaging:
    """One row of silver.yc_listings. See docs/entities.md's YcListingStaging."""

    stable_id: str
    company_name_raw: str
    website: str | None
    signal_type: str
    stage: str | None
    description: str
    occurred_on: datetime
    url: str


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
