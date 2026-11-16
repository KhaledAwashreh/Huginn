"""Intent to save the exact owned assessment the person saw."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class SaveRecommendationRequest:
    recommendation_id: UUID
    assessment_revision_id: UUID
    request_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.recommendation_id, UUID) or not isinstance(
            self.assessment_revision_id, UUID
        ):
            raise ValidationDomainError(
                "Save requires recommendation and assessment UUIDs"
            )
