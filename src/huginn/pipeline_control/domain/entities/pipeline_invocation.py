from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.pipeline_control.domain.value_objects.invocation_state import (
    InvocationState,
)
from huginn.pipeline_control.domain.value_objects.stage_plan import StagePlan


@dataclass(frozen=True)
class PipelineInvocation:
    id: UUID
    requester_account_id: UUID
    request_id: UUID
    state: InvocationState
    requested_at: datetime
    plan: StagePlan
    company_results_tracking_state: str = "tracked"
    started_at: datetime | None = None
    finished_at: datetime | None = None
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    safe_error_code: str | None = None
