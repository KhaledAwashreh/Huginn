from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.matchmaking.domain.value_objects._ranking_validation import (
    aware,
    require,
    text,
)


@dataclass(frozen=True)
class RankingObservation:
    observation_id: UUID
    description: str
    occurred_at: datetime | None
    observed_at: datetime | None
    source: str
    source_url: str

    def __post_init__(self) -> None:
        require(isinstance(self.observation_id, UUID), "Invalid observation identifier")
        for name in ("description", "source", "source_url"):
            text(getattr(self, name), name)
        for name in ("occurred_at", "observed_at"):
            value = getattr(self, name)
            if value is not None:
                aware(value, name)
