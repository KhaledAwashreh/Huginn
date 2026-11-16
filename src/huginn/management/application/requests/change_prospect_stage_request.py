from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage


@dataclass(frozen=True, slots=True)
class ChangeProspectStageRequest:
    prospect_id: UUID
    expected_version: int
    target_stage: ProspectStage
    occurred_at: datetime
    request_key: str
    reason: str | None = None

    def __post_init__(self) -> None:
        _validate(
            self.prospect_id, self.expected_version, self.occurred_at, self.request_key
        )
        if not isinstance(self.target_stage, ProspectStage):
            raise ValidationDomainError("Target stage must use its domain value")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ValidationDomainError("Stage reason must be text")


def _validate(prospect_id, expected_version, occurred_at, request_key) -> None:
    if not isinstance(prospect_id, UUID):
        raise ValidationDomainError("Prospect ID must be a UUID")
    if type(expected_version) is not int or expected_version < 1:
        raise ValidationDomainError("Expected prospect version must be positive")
    _aware(occurred_at)
    _key(request_key)


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
