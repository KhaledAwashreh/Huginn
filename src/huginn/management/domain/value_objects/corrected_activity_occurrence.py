"""Effective timestamp of an original activity and its append-only corrections."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class CorrectedActivityOccurrence:
    original_activity_id: UUID
    effective_occurred_at: datetime
    correction_head_id: UUID | None
    correction_sequence: int

    def __post_init__(self) -> None:
        if not isinstance(self.original_activity_id, UUID):
            raise ValidationDomainError("Original activity ID must be a UUID")
        if not isinstance(self.effective_occurred_at, datetime) or not _aware(
            self.effective_occurred_at
        ):
            raise ValidationDomainError(
                "Effective occurrence time must include a timezone"
            )
        if self.correction_head_id is not None and not isinstance(
            self.correction_head_id, UUID
        ):
            raise ValidationDomainError("Correction head ID must be a UUID")
        if type(self.correction_sequence) is not int or self.correction_sequence < 0:
            raise ValidationDomainError("Correction sequence must be nonnegative")
        if (self.correction_sequence == 0) != (self.correction_head_id is None):
            raise ValidationDomainError("Correction head and sequence must agree")


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None
