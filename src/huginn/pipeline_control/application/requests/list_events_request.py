from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ListEventsRequest:
    invocation_id: UUID
    after_sequence: int = 0
    limit: int = 50
