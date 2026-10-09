from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class GetInvocationRequest:
    invocation_id: UUID
