from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReconcileRunRequest:
    run_id: UUID
    executor_stopped: bool
