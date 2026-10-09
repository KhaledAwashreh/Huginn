from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ListSkippedStrategiesRequest:
    run_id: UUID
    user_id: UUID
    limit: int = 50
    offset: int = 0
