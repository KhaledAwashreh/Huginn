from dataclasses import dataclass

from huginn.matchmaking_control.domain.value_objects.run_state import RunState


@dataclass(frozen=True)
class ListRunsRequest:
    limit: int = 50
    offset: int = 0
    state: RunState | None = None
