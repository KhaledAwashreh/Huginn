"""Truthful current lifecycle returned by an offer-preparation request/retry."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus


@dataclass(frozen=True, slots=True)
class PreparedRecommendationOfferResponse:
    offer_cycle_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    status: OfferCycleStatus
    claim_token: str | None
    lease_expires_at: datetime | None
    presented_at: datetime | None

    def __post_init__(self) -> None:
        if self.status.value == "preparing":
            if not self.claim_token or self.lease_expires_at is None:
                raise ValidationDomainError("Preparing response requires a live claim")
        elif self.claim_token is not None or self.lease_expires_at is not None:
            raise ValidationDomainError("Terminal offer response cannot expose a claim")
