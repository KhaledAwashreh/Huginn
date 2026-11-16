from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class DigestSubscription:
    business_id: UUID
    user_id: UUID
    recipient: str = field(repr=False)
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.business_id, UUID) or not isinstance(self.user_id, UUID):
            raise ValueError("Digest subscription requires Business and User IDs")
        if not isinstance(self.recipient, str) or not self.recipient.strip():
            raise ValueError("Digest subscription requires a verified recipient")
        if (
            not isinstance(self.updated_at, datetime)
            or self.updated_at.tzinfo is None
            or self.updated_at.utcoffset() is None
        ):
            raise ValueError("Digest subscription timestamp must include a timezone")
        object.__setattr__(self, "updated_at", self.updated_at.astimezone(UTC))

    @property
    def version(self) -> str:
        return self.updated_at.isoformat()
