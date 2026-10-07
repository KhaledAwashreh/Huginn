from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class MatchmakingRequest:
    user_id: UUID
    cutoff: datetime
    as_of: datetime | None = None
