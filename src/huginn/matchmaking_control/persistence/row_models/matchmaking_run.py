from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class MatchmakingRunRow:
    id: UUID
    requester_account_id: UUID
    request_id: UUID
    canonical_request: dict[str, object]
    target_kind: str
    cutoff: datetime
    as_of: datetime
    state: str
    requested_at: datetime
    target_count: int
    settled_target_count: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    safe_error_code: str | None = None
