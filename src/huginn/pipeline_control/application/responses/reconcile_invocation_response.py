from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReconcileInvocationResponse:
    invocation_id: UUID
    status: str
