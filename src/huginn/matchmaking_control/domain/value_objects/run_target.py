from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking_control.domain.value_objects.target_state import TargetState


@dataclass(frozen=True)
class RunTarget:
    user_id: UUID
    ordinal: int
    state: TargetState

    @property
    def is_settled(self) -> bool:
        return self.state.is_settled
