from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.pipeline_control.presentation.api.responses.metric import MetricResponse


class EventEntryResponse(ResponseModel):
    id: UUID
    sequence: int
    occurred_at: datetime
    kind: str
    safe_code: str | None
    safe_message: str | None
    stage_name: str | None
    source_name: str | None
    metrics: list[MetricResponse]
