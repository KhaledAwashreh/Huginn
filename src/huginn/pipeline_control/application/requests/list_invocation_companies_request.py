from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ListInvocationCompaniesRequest:
    invocation_id: UUID
    limit: int = 20
    offset: int = 0
