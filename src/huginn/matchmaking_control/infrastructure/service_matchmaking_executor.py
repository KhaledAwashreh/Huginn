"""Adapt the existing matcher without importing its policy into control services."""

import logging
from uuid import UUID

from huginn.matchmaking.application.errors.execution import (
    CommitOutcomeUnknownExecutionError,
    MatchmakingExecutionError,
)
from huginn.matchmaking.application.requests.matchmaking_request import (
    MatchmakingRequest,
)
from huginn.matchmaking_control.application.read_models.skipped_strategy_result import (
    SkippedStrategyResult,
)
from huginn.matchmaking_control.application.read_models.user_result import UserResult
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState

logger = logging.getLogger(__name__)


class ServiceMatchmakingExecutor:
    def __init__(self, service):
        self._service = service

    def execute(self, user_id, cutoff, as_of):
        try:
            response = self._service.execute(MatchmakingRequest(user_id, cutoff, as_of))
        except MatchmakingExecutionError as exc:
            state = (
                TargetState.COMMIT_OUTCOME_UNKNOWN
                if isinstance(exc, CommitOutcomeUnknownExecutionError)
                else TargetState.FAILED
            )
            return UserResult(
                UUID(int=0), user_id, 0, state, safe_reason=exc.reason
            ), ()
        except Exception as exc:
            logger.warning("Matching target failed (%s)", type(exc).__name__)
            return UserResult(
                UUID(int=0),
                user_id,
                0,
                TargetState.FAILED,
                safe_reason="execution_failed",
            ), ()
        state = TargetState(response.status.value)
        if state != TargetState.SUCCEEDED:
            return UserResult(
                UUID(int=0), user_id, 0, state, safe_reason=state.value
            ), ()
        return UserResult(
            UUID(int=0),
            user_id,
            0,
            state,
            strategies_evaluated=response.strategies_evaluated,
            strategies_skipped=response.strategies_skipped,
            unique_candidates_count=response.unique_candidates_count,
            created_matches_count=len(response.created_matches),
            existing_matches_skipped_count=response.existing_matches_skipped_count,
        ), tuple(
            SkippedStrategyResult(value.strategy_id, value.reason.value)
            for value in response.skipped_strategies
        )
