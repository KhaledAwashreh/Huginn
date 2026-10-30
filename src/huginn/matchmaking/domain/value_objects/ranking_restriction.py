from dataclasses import dataclass

from huginn.matchmaking.domain.value_objects._ranking_validation import require, text
from huginn.matchmaking.domain.value_objects.ranking_evidence import RankingEvidence


@dataclass(frozen=True)
class RankingRestriction:
    scope: str
    status: str
    applies_to_hypothesis: bool
    reason: str
    evidence: RankingEvidence

    def __post_init__(self) -> None:
        require(
            self.scope
            in ("proposed_engagement", "advertised_job", "contact_route", "unknown"),
            "Invalid restriction scope",
        )
        require(
            self.status in ("conflict", "compatible", "unknown"),
            "Invalid restriction status",
        )
        require(
            type(self.applies_to_hypothesis) is bool,
            "Restriction applicability must be boolean",
        )
        text(self.reason, "Restriction reason")
        require(
            isinstance(self.evidence, RankingEvidence), "Restriction evidence required"
        )
