from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReconcileRunResponse:
    run_id: UUID
    reconciled: bool
