from datetime import datetime
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
from huginn.matchmaking_control.domain.value_objects.requester import Requester
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState


class RunRepository(Protocol):
    def latest_owner_result(self, user_id: UUID) -> dict[str, object] | None: ...

    def admit_run(
        self,
        *,
        requester: Requester,
        request_id: UUID,
        canonical_request: dict[str, object],
        target_kind: str,
        user_id: UUID | None,
        cutoff: datetime,
        as_of: datetime,
        requested_at: datetime,
    ) -> tuple[MatchmakingRun, bool]: ...
    def list_runs(
        self, limit: int, offset: int, state: RunState | None = None
    ) -> Page[RunSummary]: ...
    def get_run(self, run_id: UUID) -> RunDetail | None: ...
    def get_run_snapshot(self, run_id: UUID) -> MatchmakingRun | None: ...
    def get_target(self, run_id: UUID, user_id: UUID) -> UserResult | None: ...
    def list_user_results(
        self, run_id: UUID, limit: int, offset: int, state: TargetState | None = None
    ) -> Page[UserResult] | None: ...
    def list_skipped_strategies(
        self, run_id: UUID, user_id: UUID, limit: int, offset: int
    ) -> Page[SkippedStrategyResult] | None: ...
    def claim_next_run(
        self, worker_id: UUID, now: datetime
    ) -> MatchmakingRun | None: ...
    def start_run(self, run_id: UUID, worker_id: UUID, now: datetime) -> bool: ...
    def start_target(
        self, run_id: UUID, user_id: UUID, worker_id: UUID, now: datetime
    ) -> bool: ...
    def acknowledge_target(
        self,
        result: UserResult,
        skipped: tuple[SkippedStrategyResult, ...],
        worker_id: UUID,
        now: datetime,
    ) -> bool: ...
    def pending_targets(
        self, run_id: UUID, worker_id: UUID
    ) -> tuple[UserResult, ...]: ...
    def finish_run(
        self, run_id: UUID, worker_id: UUID, finished_at: datetime
    ) -> bool: ...
    def reconcile_run(
        self, run_id: UUID, worker_id: UUID, finished_at: datetime
    ) -> bool: ...
    def heartbeat(self, run_id: UUID, worker_id: UUID, now: datetime) -> bool: ...
