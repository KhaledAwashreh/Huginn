from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.pipeline_control.presentation.api.responses.source_execution import (
    SourceExecutionResponse,
)
from huginn.pipeline_control.presentation.api.responses.stage_execution import (
    StageExecutionResponse,
)


class InvocationDetailResponse(ResponseModel):
    id: UUID
    requester_account_id: UUID
    state: str
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    safe_error_code: str | None
    request_id: UUID
    heartbeat_at: datetime | None
    tracking_state: str
    stages: list[StageExecutionResponse]
    sources: list[SourceExecutionResponse]
