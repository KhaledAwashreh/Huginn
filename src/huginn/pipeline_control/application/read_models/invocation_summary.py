from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class InvocationSummary:
    id: UUID
    requester_account_id: UUID
    state: str
    requested_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    safe_error_code: str | None
