from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.matchmaking_control.domain.value_objects.run_state import RunState


class RunReceiptResponse(ResponseModel):
    id: UUID
    state: RunState
    requested_at: datetime
    cutoff: datetime
    as_of: datetime
    target_count: int
