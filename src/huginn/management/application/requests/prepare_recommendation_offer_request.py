"""Owner intent to claim one exact, previously selected assessment for display."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class PrepareRecommendationOfferRequest:
    recommendation_id: UUID
    assessment_revision_id: UUID
    request_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.recommendation_id, UUID) or not isinstance(
            self.assessment_revision_id, UUID
        ):
            raise ValidationDomainError(
                "Offer requires recommendation and revision IDs"
            )
        if (
            not isinstance(self.request_key, str)
            or not self.request_key.strip()
            or len(self.request_key) > 200
        ):
            raise ValidationDomainError("Offer preparation request key is invalid")
