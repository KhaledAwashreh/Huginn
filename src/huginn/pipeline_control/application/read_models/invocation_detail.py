from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.pipeline_control.application.read_models.source_execution import (
    SourceExecution,
)
from huginn.pipeline_control.application.read_models.stage_execution import (
    StageExecution,
)


@dataclass(frozen=True)
class InvocationDetail:
    id: UUID
    requester_account_id: UUID
    request_id: UUID
    state: str
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    heartbeat_at: datetime | None
    tracking_state: str
    stages: tuple[StageExecution, ...]
    sources: tuple[SourceExecution, ...]
    safe_error_code: str | None
