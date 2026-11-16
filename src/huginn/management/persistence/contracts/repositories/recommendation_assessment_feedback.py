from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.recommendation_assessment_feedback import (
    RecommendationAssessmentFeedback,
)


class RecommendationAssessmentFeedbackRepository(Protocol):
    def list_for_revision(
        self, business_id: UUID, recommendation_id: UUID, revision_id: UUID
    ) -> tuple[RecommendationAssessmentFeedback, ...]: ...
    def append(
        self, feedback: RecommendationAssessmentFeedback
    ) -> RecommendationAssessmentFeedback:
        """Attribute feedback to the exact shown revision; never mutate pursuit/ranking."""
        ...
