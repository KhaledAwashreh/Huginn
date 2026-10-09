from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.matchmaking_control.domain.value_objects.run_state import RunState


class RunDetailResponse(ResponseModel):
    id: UUID
    request_id: UUID
    requester_account_id: UUID
    target_kind: str
    state: RunState
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    cutoff: datetime
    as_of: datetime
    target_count: int
    settled_target_count: int
    heartbeat_at: datetime | None
    safe_error_code: str | None
    succeeded_count: int
    skipped_count: int
    failed_count: int
    uncertain_count: int
    not_executed_count: int
    created_matches_count: int | None
    existing_matches_skipped_count: int | None
    counts_complete: bool
    tracking_stale: bool
    current_user_id: UUID | None
