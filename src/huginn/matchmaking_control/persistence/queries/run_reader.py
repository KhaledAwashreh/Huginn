from collections.abc import Callable
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
from huginn.matchmaking_control.persistence.contracts.unit_of_work import (
    MatchmakingControlUnitOfWork,
)


class PostgresRunReader:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], MatchmakingControlUnitOfWork],
        clock: object | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock

    def latest_owner_result(self, user_id: UUID) -> dict[str, object] | None:
        with self._uow_factory() as uow:
            return uow.runs.latest_owner_result(user_id)

    def list_runs(
        self, limit: int, offset: int, state: RunState | None = None
    ) -> Page[RunSummary]:
        with self._uow_factory() as uow:
            return uow.runs.list_runs(limit, offset, state)

    def get_run(self, run_id: UUID) -> RunDetail | None:
        with self._uow_factory() as uow:
            return uow.runs.get_run(run_id)

    def list_user_results(
        self, run_id: UUID, limit: int, offset: int, state: TargetState | None = None
    ) -> Page[UserResult] | None:
        with self._uow_factory() as uow:
            return uow.runs.list_user_results(run_id, limit, offset, state)

    def list_skipped_strategies(
        self, run_id: UUID, user_id: UUID, limit: int, offset: int
    ) -> Page[SkippedStrategyResult] | None:
        with self._uow_factory() as uow:
            return uow.runs.list_skipped_strategies(run_id, user_id, limit, offset)

    def get_run_snapshot(self, run_id: UUID) -> MatchmakingRun | None:
        with self._uow_factory() as uow:
            return uow.runs.get_run_snapshot(run_id)
