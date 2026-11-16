"""User judgment of one exact recommendation assessment."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)


@dataclass(frozen=True, slots=True)
class RecordRecommendationFeedbackRequest:
    recommendation_id: UUID
    assessment_revision_id: UUID
    request_key: str
    feedback: RecommendationFeedback

    def __post_init__(self) -> None:
        if not isinstance(self.recommendation_id, UUID) or not isinstance(
            self.assessment_revision_id, UUID
        ):
            raise ValidationDomainError(
                "Feedback requires recommendation and assessment UUIDs"
            )
        if not isinstance(self.request_key, str) or not self.request_key.strip():
            raise ValidationDomainError("Feedback request key is required")
        if not isinstance(self.feedback, RecommendationFeedback):
            raise ValidationDomainError(
                "Feedback must use the validated recommendation feedback value"
            )
