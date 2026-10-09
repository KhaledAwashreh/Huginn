from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.matchmaking_control.domain.value_objects.run_state import RunState


class RunSummaryResponse(ResponseModel):
    id: UUID
    requester_account_id: UUID
    state: RunState
    requested_at: datetime
    cutoff: datetime
    as_of: datetime
    target_count: int
    settled_target_count: int
