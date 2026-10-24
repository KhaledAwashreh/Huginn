"""Resolved signal projection consumed by Gold company-signal writes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ResolvedSignalForFact:
    """One silver.resolved_signals row already joined to its gold.company
    row, ready to become one gold.company_signal row. See docs/entities.md's
    CompanySignal and ADR-0007. Only domain-normalized signals with a
    matching gold.company row produce one of these, enforced by the read
    query's join, not here.
    """

    company_id: str
    source: str
    source_stable_id: str
    signal_type: str
    source_url: str | None
    stage: str | None
    description: str | None
    occurred_at: datetime
