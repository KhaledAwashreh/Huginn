from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class DigestSubscription:
    user_id: UUID
    strategy_id: UUID
    recipient: str = field(repr=False)
