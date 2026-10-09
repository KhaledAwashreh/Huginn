from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.pipeline_control.domain.constants.event_kinds import ALLOWED_EVENT_KINDS
from huginn.pipeline_control.domain.value_objects.metric import Metric


@dataclass(frozen=True)
class PipelineEvent:
    invocation_id: UUID
    kind: str
    occurred_at: datetime
    safe_code: str | None = None
    safe_message: str | None = None
    stage_name: str | None = None
    source_name: str | None = None
    metrics: tuple[Metric, ...] = ()

    def __post_init__(self) -> None:
        if self.kind not in ALLOWED_EVENT_KINDS:
            raise ValueError("event kind is not allowlisted")
