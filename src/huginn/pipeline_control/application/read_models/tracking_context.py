from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class TrackingContext:
    invocation_id: UUID
    stage_job_run_id: UUID
    stage_name: str
