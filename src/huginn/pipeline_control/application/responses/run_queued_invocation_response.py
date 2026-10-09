from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class RunQueuedInvocationResponse:
    invocation_id: UUID | None
    status: str
