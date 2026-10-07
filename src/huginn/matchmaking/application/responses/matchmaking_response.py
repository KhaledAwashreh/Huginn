from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from huginn.matchmaking.application.responses.skipped_strategy import SkippedStrategy
from huginn.matchmaking.domain.entities.match import Match


class MatchmakingStatus(StrEnum):
    SUCCEEDED = "succeeded"
    DISABLED_USER = "disabled_user"
    USER_NOT_FOUND = "user_not_found"


@dataclass(frozen=True)
class MatchmakingResponse:
    user_id: UUID
    status: MatchmakingStatus
    cutoff: datetime
    as_of: datetime
    strategies_evaluated: int
    strategies_skipped: int
    unique_candidates_count: int
    created_matches: tuple[Match, ...]
    existing_matches_skipped_count: int
    skipped_strategies: tuple[SkippedStrategy, ...]
