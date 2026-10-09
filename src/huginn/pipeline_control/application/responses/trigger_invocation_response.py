from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class TriggerInvocationResponse:
    id: UUID
    status: str
    requested_at: datetime
    created: bool
