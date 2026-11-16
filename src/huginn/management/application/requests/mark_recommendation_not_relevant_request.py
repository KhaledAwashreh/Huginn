"""Intent to reject an exact owned recommendation shown to the User."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class MarkRecommendationNotRelevantRequest:
    recommendation_id: UUID
    assessment_revision_id: UUID
    expected_recommendation_version: int
    request_key: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.recommendation_id, UUID) or not isinstance(
            self.assessment_revision_id, UUID
        ):
            raise ValidationDomainError(
                "Rejection requires recommendation and revision IDs"
            )
        if (
            type(self.expected_recommendation_version) is not int
            or self.expected_recommendation_version < 1
        ):
            raise ValidationDomainError(
                "Expected recommendation version must be positive"
            )
        if type(self.request_key) is not str or not self.request_key.strip():
            raise ValidationDomainError("Request key is required")
        if self.reason is not None and type(self.reason) is not str:
            raise ValidationDomainError("Rejection reason must be text")
