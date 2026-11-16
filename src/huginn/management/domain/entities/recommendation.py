from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)


@dataclass(frozen=True)
class Recommendation:
    id: UUID
    business_id: UUID
    company_id: UUID
    status: RecommendationStatus
    created_at: datetime
    updated_at: datetime
    current_revision_id: UUID | None = None
    first_presented_at: datetime | None = None
    resolved_at: datetime | None = None
    resolved_by_user_id: UUID | None = None
    resolution_reason: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (self.id, self.business_id, self.company_id)
        ):
            raise ValidationDomainError("Recommendation identities must be UUIDs")
        if not isinstance(self.status, RecommendationStatus):
            raise ValidationDomainError(
                "Recommendation status must use its domain value"
            )
        if type(self.version) is not int or self.version < 1:
            raise ValidationDomainError("Recommendation version must be positive")
        _aware(self.created_at, "created_at")
        _aware(self.updated_at, "updated_at")
        for name in ("first_presented_at", "resolved_at"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if (self.status.value == "open") != (self.resolved_at is None):
            raise ValidationDomainError(
                "Only resolved recommendations have a resolution time"
            )
        if self.status.value == "open" and any(
            value is not None
            for value in (self.resolved_by_user_id, self.resolution_reason)
        ):
            raise ValidationDomainError("Open recommendations cannot have a resolution")
        if self.status.value != "open" and self.resolved_by_user_id is None:
            raise ValidationDomainError(
                "Resolved recommendations require an acting User"
            )
        if self.resolved_by_user_id is not None and not isinstance(
            self.resolved_by_user_id, UUID
        ):
            raise ValidationDomainError("Resolution actor must be a User UUID")


def _aware(value: datetime, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError(f"{name} must include a timezone")
