from dataclasses import dataclass
from datetime import datetime

from huginn.matchmaking.domain.constants.research_ranking import (
    CONFIDENCE_ORDER,
    RESEARCH_RANKING_VERSION,
)
from huginn.matchmaking.domain.value_objects._ranking_validation import aware, require
from huginn.matchmaking.domain.value_objects.ranking_assessment import RankingAssessment


@dataclass(frozen=True)
class RankingScore:
    assessment: RankingAssessment
    version: str
    as_of: datetime
    service_points: int
    context_points: int
    preference_points: int
    timing_points: int
    confidence: str
    excluded: bool
    restriction_disposition: str

    def __post_init__(self) -> None:
        require(
            isinstance(self.assessment, RankingAssessment),
            "Assessment snapshot required",
        )
        require(self.version == RESEARCH_RANKING_VERSION, "Unsupported scoring version")
        aware(self.as_of, "as_of")
        for name, cap in (
            ("service_points", 40),
            ("context_points", 30),
            ("preference_points", 15),
            ("timing_points", 15),
        ):
            value = getattr(self, name)
            require(
                type(value) is int and 0 <= value <= cap, "Invalid scoring component"
            )
        require(self.confidence in CONFIDENCE_ORDER, "Invalid confidence")
        require(type(self.excluded) is bool, "Exclusion must be boolean")
        require(
            self.restriction_disposition
            in ("none", "excluded", "not_applicable", "unresolved"),
            "Invalid restriction disposition",
        )
        require(
            self.excluded == (self.restriction_disposition == "excluded"),
            "Inconsistent exclusion disposition",
        )

    @property
    def total(self) -> int:
        return (
            self.service_points
            + self.context_points
            + self.preference_points
            + self.timing_points
        )

    @property
    def service_scoring_mode(self) -> str:
        return (
            "semantic_logit"
            if self.assessment.semantic_service_logit is not None
            else "assessed_label"
        )
