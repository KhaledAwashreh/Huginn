from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.pipeline_control.presentation.api.responses.metric import MetricResponse


class SourceExecutionResponse(ResponseModel):
    name: str
    job_run_id: UUID
    parent_job_run_id: UUID
    state: str
    started_at: datetime
    finished_at: datetime | None
    metrics: list[MetricResponse]
    safe_error_code: str | None
