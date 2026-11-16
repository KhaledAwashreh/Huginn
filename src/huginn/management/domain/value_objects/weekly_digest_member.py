"""Exact immutable recommendation, assessment and cycle in one email position."""

from dataclasses import dataclass
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class WeeklyDigestMember:
    company_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    offer_cycle_id: UUID
    position: int

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (
                self.company_id,
                self.recommendation_id,
                self.assessment_revision_id,
                self.offer_cycle_id,
            )
        ):
            raise ValidationDomainError("Digest membership requires exact UUIDs")
        if type(self.position) is not int or not 1 <= self.position <= 7:
            raise ValidationDomainError("Digest position must be between one and seven")
