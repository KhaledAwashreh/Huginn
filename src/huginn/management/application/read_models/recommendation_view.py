"""Historical assessment and explicitly separate current discovery context."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.entities.suppression_block import SuppressionBlock
from huginn.matchmaking.domain.policies.recommendation_eligibility import (
    assess_recommendation_eligibility,
)
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)


@dataclass(frozen=True, slots=True)
class RecommendationView:
    recommendation: Recommendation
    company: CurrentCompany
    assessment: AssessmentRevision | None
    prospect: Prospect | None
    selection_state: BusinessCompanyState
    read_at: datetime
    evidence_state: Literal["current", "changed", "unavailable", "not_assessed"]
    active_blocks: tuple[SuppressionBlock, ...] = ()

    assessment_presented_at: datetime | None = None

    @property
    def selection_blockers(self) -> tuple[str, ...]:
        return assess_recommendation_eligibility(
            self.selection_state, self.read_at
        ).blockers

    @property
    def current_eligibility(self) -> str:
        if self.recommendation.status.value != "open":
            return "historical"
        if self.selection_blockers:
            return "blocked"
        if self.evidence_state != "current":
            return "unavailable"
        return "not_reassessed"
