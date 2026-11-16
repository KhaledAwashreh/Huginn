from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.suppression_kind import SuppressionKind


@dataclass(frozen=True)
class SuppressionBlock:
    id: UUID
    business_id: UUID
    company_id: UUID
    kind: SuppressionKind
    created_at: datetime
    effective_at: datetime | None = None
    created_by_user_id: UUID | None = None
    expires_at: datetime | None = None
    cleared_at: datetime | None = None
    cleared_by_user_id: UUID | None = None
    reason: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.kind, SuppressionKind):
            raise ValidationDomainError("Suppression kind must use its domain value")
        for name in ("created_at", "effective_at", "expires_at", "cleared_at"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValidationDomainError(f"{name} must include a timezone")
        if self.effective_at is None:
            object.__setattr__(self, "effective_at", self.created_at)
        if self.effective_at > self.created_at:
            raise ValidationDomainError("Effective time cannot follow recording time")
        if (self.cleared_at is None) != (self.cleared_by_user_id is None):
            raise ValidationDomainError(
                "Clearing a block requires an acting User and time"
            )
        if self.kind.value == "cooldown" and self.expires_at is None:
            raise ValidationDomainError("Cooldown must have a finite expiry")
        if self.kind.value == "rejection" and self.expires_at is not None:
            raise ValidationDomainError("Rejection cannot expire")
        if self.expires_at is not None and self.expires_at <= self.effective_at:
            raise ValidationDomainError("Suppression expiry must follow effective time")
        if self.cleared_at is not None and self.cleared_at < self.created_at:
            raise ValidationDomainError("Block cannot be cleared before creation")
        if (
            self.kind.value in {"rejection", "pause"}
            and self.created_by_user_id is None
        ):
            raise ValidationDomainError(
                "User suppression decisions require an acting User"
            )
        if type(self.version) is not int or self.version < 1:
            raise ValidationDomainError("Suppression block version must be positive")

    def is_active_at(self, at: datetime) -> bool:
        if not isinstance(at, datetime) or at.tzinfo is None or at.utcoffset() is None:
            raise ValidationDomainError("Evaluation time must include a timezone")
        return (
            self.effective_at <= at
            and self.cleared_at is None
            and (self.expires_at is None or at < self.expires_at)
        )
