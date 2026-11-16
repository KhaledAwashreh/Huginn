from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class CorrectProspectActivityTimeRequest:
    prospect_id: UUID
    expected_version: int
    original_activity_id: UUID
    expected_correction_head_id: UUID | None
    replacement_occurred_at: datetime
    request_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.prospect_id, UUID) or not isinstance(
            self.original_activity_id, UUID
        ):
            raise ValidationDomainError(
                "Prospect and original activity IDs must be UUIDs"
            )
        if type(self.expected_version) is not int or self.expected_version < 1:
            raise ValidationDomainError("Expected prospect version must be positive")
        if self.expected_correction_head_id is not None and not isinstance(
            self.expected_correction_head_id, UUID
        ):
            raise ValidationDomainError("Expected correction head must be a UUID")
        _aware(self.replacement_occurred_at)
        if not isinstance(self.request_key, str) or not self.request_key.strip():
            raise ValidationDomainError("Request key is required")


def _aware(value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError("Corrected occurrence time must include a timezone")
