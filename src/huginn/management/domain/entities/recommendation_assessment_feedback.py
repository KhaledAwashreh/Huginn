from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)


@dataclass(frozen=True)
class RecommendationAssessmentFeedback:
    id: UUID
    business_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    actor_user_id: UUID
    recorded_at: datetime
    feedback: RecommendationFeedback

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (
                self.id,
                self.business_id,
                self.recommendation_id,
                self.assessment_revision_id,
                self.actor_user_id,
            )
        ):
            raise ValidationDomainError("Feedback attribution identities must be UUIDs")
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValidationDomainError("Feedback time must include a timezone")
        if not isinstance(self.feedback, RecommendationFeedback):
            raise ValidationDomainError("Feedback must use its existing domain value")
