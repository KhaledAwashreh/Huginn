from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True)
class ProspectOrigin:
    id: UUID
    business_id: UUID
    company_id: UUID
    prospect_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    created_by_user_id: UUID
    created_at: datetime

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (
                self.id,
                self.business_id,
                self.company_id,
                self.prospect_id,
                self.recommendation_id,
                self.assessment_revision_id,
                self.created_by_user_id,
            )
        ):
            raise ValidationDomainError("Origin identities must be UUIDs")
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
        ):
            raise ValidationDomainError("Origin time must include a timezone")
