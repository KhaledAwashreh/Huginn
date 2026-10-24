"""Gold data shapes. See architecture document section 5.

Separated from `ports.py` so the protocols file holds contracts only,
matching the `models.py` / `ports.py` / `repositories/` shape Bronze and
Silver already use.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DomainNormalizedSignal:
    """One silver.resolved_signals row with a cleanly derived domain, read
    for building or updating a gold.company row. See docs/entities.md's
    ResolvedSignal and architecture document section 6 (key_derivation
    bands): only `domain_normalized` rows carry a durable domain key, a
    placeholder key awaiting manual review is not a company identity yet.
    """

    domain: str
    source: str
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
    founded: str | None = None
    total_funding: str | None = None
