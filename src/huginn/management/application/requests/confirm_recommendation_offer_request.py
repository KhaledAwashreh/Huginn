"""Capability to confirm one prepared recommendation after actual display."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class ConfirmRecommendationOfferRequest:
    offer_cycle_id: UUID
    claim_token: str

    def __post_init__(self) -> None:
        if not isinstance(self.offer_cycle_id, UUID):
            raise ValidationDomainError("Offer cycle ID must be a UUID")
        if not isinstance(self.claim_token, str) or not self.claim_token.strip():
            raise ValidationDomainError("Offer claim token is required")
