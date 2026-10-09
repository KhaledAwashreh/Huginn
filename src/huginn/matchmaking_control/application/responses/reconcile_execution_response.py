from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReconcileExecutionResponse:
    execution_id: UUID
    reconciled: bool
