"""Gold data shapes. See architecture document section 5.

Separated from `ports.py` so the protocols file holds contracts only,
matching the `models.py` / `ports.py` / `repositories/` shape Bronze and
Silver already use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class DomainNormalizedSignal:
    """One silver.resolved_signals row with a cleanly derived domain, read
    for building or updating a gold.company row. See docs/entities.md's
    ResolvedSignal and architecture document section 6 (key_derivation
    bands): only `domain_normalized` rows carry a durable domain key, a
    placeholder key awaiting manual review is not a company identity yet.
    """

    domain: str
    company_name_raw: str
    stage: str | None = None
    company_status: str | None = None
    team_size: int | None = None
    # YC's `industries` as a list, and its `all_locations` display string.
    # Both are the source's own shape; Gold turns them into
    # business_sector and country/city (see gold.company.parse_all_locations).
    industries: list[str] | None = None
    all_locations: str | None = None
    # YC's funded batch, e.g. 'Summer 2023', carried verbatim from Silver.
    # Gold prefixes it to form gold.company.notes.
    batch: str | None = None


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
