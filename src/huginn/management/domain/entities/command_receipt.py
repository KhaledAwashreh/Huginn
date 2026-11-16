from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot


@dataclass(frozen=True)
class CommandReceipt:
    business_id: UUID
    scope: str
    identity: CommandIdentity
    resource_kind: str
    resource_id: UUID
    resource_version: int
    result_snapshot: JsonSnapshot
    recorded_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.business_id, UUID) or not isinstance(
            self.resource_id, UUID
        ):
            raise ValidationDomainError("Command receipt identities must be UUIDs")
        if not self.scope.strip() or not self.resource_kind.strip():
            raise ValidationDomainError(
                "Command receipt scope and resource kind are required"
            )
        if not isinstance(self.identity, CommandIdentity):
            raise ValidationDomainError("Command receipt needs a stable identity")
        if type(self.resource_version) is not int or self.resource_version < 1:
            raise ValidationDomainError("Command result version must be positive")
        if not isinstance(self.result_snapshot, JsonSnapshot):
            object.__setattr__(
                self, "result_snapshot", JsonSnapshot(self.result_snapshot)
            )
        if (
            not isinstance(self.recorded_at, datetime)
            or self.recorded_at.tzinfo is None
            or self.recorded_at.utcoffset() is None
        ):
            raise ValidationDomainError("Command receipt time must include a timezone")
