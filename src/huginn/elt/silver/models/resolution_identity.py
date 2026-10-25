from dataclasses import dataclass


@dataclass(frozen=True)
class ResolutionIdentity:
    """A prior domain-normalized identity; see ADR-0018."""

    source: str
    source_stable_id: str
    resolved_company_key: str
