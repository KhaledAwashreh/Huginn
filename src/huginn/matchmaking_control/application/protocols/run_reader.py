from typing import Protocol
from uuid import UUID

from huginn.management.domain.value_objects.common import Page
from huginn.matchmaking_control.application.read_models.run_detail import RunDetail
from huginn.matchmaking_control.application.read_models.run_summary import RunSummary
from huginn.matchmaking_control.application.read_models.skipped_strategy_result import (
    SkippedStrategyResult,
)
from huginn.matchmaking_control.application.read_models.user_result import UserResult
from huginn.matchmaking_control.domain.entities.matchmaking_run import MatchmakingRun
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState


class RunReader(Protocol):
    def latest_owner_result(self, user_id: UUID) -> dict[str, object] | None: ...

    def list_runs(
        self, limit: int, offset: int, state: RunState | None = None
    ) -> Page[RunSummary]: ...
    def get_run(self, run_id: UUID) -> RunDetail | None: ...
    def list_user_results(
        self, run_id: UUID, limit: int, offset: int, state: TargetState | None = None
    ) -> Page[UserResult] | None: ...
    def list_skipped_strategies(
        self, run_id: UUID, user_id: UUID, limit: int, offset: int
    ) -> Page[SkippedStrategyResult] | None: ...
    def get_run_snapshot(self, run_id: UUID) -> MatchmakingRun | None: ...
