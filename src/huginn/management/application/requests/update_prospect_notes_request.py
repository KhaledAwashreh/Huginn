from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class UpdateProspectNotesRequest:
    prospect_id: UUID
    expected_version: int
    replacement_notes: str
    occurred_at: datetime
    request_key: str

    def __post_init__(self) -> None:
        if not isinstance(self.prospect_id, UUID):
            raise ValidationDomainError("Prospect ID must be a UUID")
        if type(self.expected_version) is not int or self.expected_version < 1:
            raise ValidationDomainError("Expected prospect version must be positive")
        if not isinstance(self.replacement_notes, str):
            raise ValidationDomainError("Prospect notes must be text")
        _aware(self.occurred_at)
        _key(self.request_key)


def _aware(value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError("Activity occurrence time must include a timezone")


def _key(value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationDomainError("Request key is required")
