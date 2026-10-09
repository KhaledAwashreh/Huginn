from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetRunRequest:
    run_id: UUID
