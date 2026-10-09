from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ExecuteRunRequest:
    run_id: UUID
    worker_id: UUID
