from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class UserResultRow:
    run_id: UUID
    user_id: UUID
    ordinal: int
    state: str
    started_at: datetime | None
    finished_at: datetime | None
    strategies_evaluated: int | None
    strategies_skipped: int | None
    unique_candidates_count: int | None
    created_matches_count: int | None
    existing_matches_skipped_count: int | None
    safe_reason: str | None
