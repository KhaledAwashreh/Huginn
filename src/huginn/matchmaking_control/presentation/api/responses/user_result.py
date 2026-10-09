from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState


class UserResultResponse(ResponseModel):
    run_id: UUID
    user_id: UUID
    ordinal: int
    state: TargetState
    started_at: datetime | None = None
    finished_at: datetime | None = None
    strategies_evaluated: int | None = None
    strategies_skipped: int | None = None
    unique_candidates_count: int | None = None
    created_matches_count: int | None = None
    existing_matches_skipped_count: int | None = None
    safe_reason: str | None = None
