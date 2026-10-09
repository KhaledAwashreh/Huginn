from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.pipeline_control.domain.value_objects.metric import Metric


@dataclass(frozen=True)
class StageExecution:
    name: str
    order: int
    dependencies: tuple[str, ...]
    state: str
    job_run_id: UUID | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    metrics: tuple[Metric, ...] = ()
    safe_error_code: str | None = None
    skip_reason: str | None = None
