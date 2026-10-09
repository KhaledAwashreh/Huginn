"""Durable administrator run snapshot; see admin-matchmaking-execution design."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.matchmaking_control.domain.value_objects.requester import Requester
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.domain.value_objects.run_target import RunTarget


@dataclass(frozen=True)
class MatchmakingRun:
    id: UUID
    requester: Requester
    request_id: UUID
    canonical_request: dict[str, object]
    target_kind: str
    cutoff: datetime
    as_of: datetime
    state: RunState
    requested_at: datetime
    target_count: int
    settled_target_count: int
    targets: tuple[RunTarget, ...] = ()
    started_at: datetime | None = None
    finished_at: datetime | None = None
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    safe_error_code: str | None = None

    @property
    def unsettled_target_count(self) -> int:
        return self.target_count - self.settled_target_count
