from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.matchmaking_control.domain.value_objects.run_state import RunState


@dataclass(frozen=True)
class TriggerRunResponse:
    id: UUID
    state: RunState
    requested_at: datetime
    cutoff: datetime
    as_of: datetime
    target_count: int
    replayed: bool = False
