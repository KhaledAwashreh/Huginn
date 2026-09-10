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
    company_name_raw: str
