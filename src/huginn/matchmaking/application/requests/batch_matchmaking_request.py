from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class BatchMatchmakingRequest:
    user_ids: tuple[UUID, ...]
    cutoff: datetime
    as_of: datetime | None = None
