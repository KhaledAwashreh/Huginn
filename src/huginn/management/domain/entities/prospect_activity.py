from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot


@dataclass(frozen=True)
class ProspectActivity:
    id: UUID
    business_id: UUID
    prospect_id: UUID
    actor_user_id: UUID
    kind: ActivityKind
    occurred_at: datetime
    recorded_at: datetime
    payload: JsonSnapshot
    correction_of_id: UUID | None = None

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (
                self.id,
                self.business_id,
                self.prospect_id,
                self.actor_user_id,
            )
        ):
            raise ValidationDomainError("Activity identities must be UUIDs")
        if not isinstance(self.kind, ActivityKind):
            raise ValidationDomainError("Activity kind must use its domain value")
        for name in ("occurred_at", "recorded_at"):
            value = getattr(self, name)
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValidationDomainError(f"{name} must include a timezone")
        if not isinstance(self.payload, JsonSnapshot):
            object.__setattr__(self, "payload", JsonSnapshot(self.payload))
        if (self.kind.value == "correction") != (self.correction_of_id is not None):
            raise ValidationDomainError(
                "Corrections must reference the activity they correct"
            )
        if (
            self.kind.value == "correction"
            and not {"prior", "replacement"} <= self.payload.value.keys()
        ):
            raise ValidationDomainError(
                "Corrections must preserve prior and replacement values"
            )
