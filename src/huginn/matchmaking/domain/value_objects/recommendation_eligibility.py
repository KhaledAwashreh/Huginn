from dataclasses import dataclass


@dataclass(frozen=True)
class RecommendationEligibility:
    eligible: bool
    blockers: tuple[str, ...]
