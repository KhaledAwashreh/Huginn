from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.matchmaking_control.application.read_models.skipped_strategy_result import (
    SkippedStrategyResult,
)
from huginn.matchmaking_control.application.read_models.user_result import UserResult


class MatchmakingExecutor(Protocol):
    def execute(
        self, user_id: UUID, cutoff: datetime, as_of: datetime
    ) -> tuple[UserResult, tuple[SkippedStrategyResult, ...]]: ...
