from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.pipeline_control.domain.value_objects.metric import Metric


@dataclass(frozen=True)
class EventEntry:
    id: UUID
    sequence: int
    occurred_at: datetime
    kind: str
    safe_code: str | None
    safe_message: str | None
    stage_name: str | None
    source_name: str | None
    metrics: tuple[Metric, ...]
