from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ReconcileInvocationRequest:
    invocation_id: UUID
    executor_stopped: bool
