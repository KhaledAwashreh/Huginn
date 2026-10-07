"""Private User availability query row, design section 2."""

from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.application.read_models.user_availability import (
    UserAvailability,
)
from huginn.matchmaking.persistence.errors.database import DataIntegrityError


@dataclass(frozen=True)
class UserAvailabilityRow:
    user_id: UUID
    account_id: UUID | None
    account_status: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.user_id, UUID):
            raise DataIntegrityError("Invalid User identifier")
        if self.account_id is not None and not isinstance(self.account_id, UUID):
            raise DataIntegrityError("Invalid Account identifier")
        if self.account_status is not None and type(self.account_status) is not str:
            raise DataIntegrityError("Invalid Account status")

    def to_read_model(self) -> UserAvailability:
        if self.account_id is None or self.account_status not in ("active", "disabled"):
            raise DataIntegrityError("Invalid Account reference or status")
        return UserAvailability(self.account_status)
