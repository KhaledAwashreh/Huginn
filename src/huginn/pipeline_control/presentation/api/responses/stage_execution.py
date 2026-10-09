from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.pipeline_control.presentation.api.responses.metric import MetricResponse


class StageExecutionResponse(ResponseModel):
    name: str
    order: int
    dependencies: list[str]
    state: str
    job_run_id: UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics: list[MetricResponse] = []
    safe_error_code: str | None = None
    skip_reason: str | None = None
