from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReconcileExecutionRequest:
    execution_id: UUID
    executor_stopped: bool
