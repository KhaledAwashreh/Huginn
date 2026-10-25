from dataclasses import dataclass


@dataclass(frozen=True)
class ResolutionRegression:
    """Aggregate or source cohort counts and per-source threshold; see ADR-0018."""

    previously_resolved: int
    downgraded: int
    max_downgrade_percent: int
    source: str | None = None
