from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.pipeline_control.domain.value_objects.metric import Metric


@dataclass(frozen=True)
class SourceExecution:
    name: str
    job_run_id: UUID
    parent_job_run_id: UUID
    state: str
    started_at: datetime
    finished_at: datetime | None
    metrics: tuple[Metric, ...] = ()
    safe_error_code: str | None = None
