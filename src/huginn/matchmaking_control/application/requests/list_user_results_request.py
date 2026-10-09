from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking_control.domain.value_objects.target_state import TargetState


@dataclass(frozen=True)
class ListUserResultsRequest:
    run_id: UUID
    limit: int = 50
    offset: int = 0
    state: TargetState | None = None
