from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ExecuteRunResponse:
    run_id: UUID
    status: str
