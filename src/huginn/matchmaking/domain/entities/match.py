from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class MatchStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    RESPONDED = "responded"
    DISMISSED = "dismissed"
    CONVERTED = "converted"


@dataclass(frozen=True)
class Match:
    id: UUID
    user_id: UUID
    company_id: UUID
    status: MatchStatus
    notes: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, UUID)
            for value in (self.id, self.user_id, self.company_id)
        ):
            raise ValueError("match identifiers must be UUIDs")
        if not isinstance(self.status, MatchStatus):
            raise ValueError("match status must be a MatchStatus")
        if not _aware(self.created_at) or not _aware(self.updated_at):
            raise ValueError("match timestamps must be timezone-aware")


def _aware(value: datetime) -> bool:
    return (
        isinstance(value, datetime)
        and value.tzinfo is not None
        and value.utcoffset() is not None
    )
