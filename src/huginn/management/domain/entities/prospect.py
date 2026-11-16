from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.prospect_stage import ProspectStage


@dataclass(frozen=True)
class Prospect:
    id: UUID
    business_id: UUID
    company_id: UUID
    stage: ProspectStage
    created_at: datetime
    updated_at: datetime
    version: int = 1
    notes: str = ""
    follow_up_at: datetime | None = None
    last_active_stage: ProspectStage | None = None

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (self.id, self.business_id, self.company_id)
        ):
            raise ValidationDomainError("Prospect identities must be UUIDs")
        if not isinstance(self.stage, ProspectStage):
            raise ValidationDomainError("Prospect stage must use its domain value")
        if type(self.version) is not int or self.version < 1:
            raise ValidationDomainError("Prospect version must be positive")
        if not isinstance(self.notes, str):
            raise ValidationDomainError("Prospect notes must be text")
        for name in ("created_at", "updated_at", "follow_up_at"):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if self.stage.value == "closed":
            if not isinstance(
                self.last_active_stage, ProspectStage
            ) or self.last_active_stage.value not in {
                "saved",
                "contacted",
                "in_conversation",
                "proposal_sent",
            }:
                raise ValidationDomainError(
                    "Closed prospect must retain its last active stage"
                )
        elif self.last_active_stage is not None:
            raise ValidationDomainError(
                "Only a closed prospect has a last active stage"
            )


def _aware(value: datetime, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError(f"{name} must include a timezone")
