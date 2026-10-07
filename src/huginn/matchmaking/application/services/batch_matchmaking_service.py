"""Sequential independent per-User transactions, matchmaking design section 8."""

from collections.abc import Callable
from uuid import UUID

from huginn.matchmaking.application.errors.execution import (
    InputValidationError,
    MatchmakingExecutionError,
)
from huginn.matchmaking.application.protocols.clock import Clock
from huginn.matchmaking.application.requests.batch_matchmaking_request import (
    BatchMatchmakingRequest,
)
from huginn.matchmaking.application.requests.matchmaking_request import (
    MatchmakingRequest,
)
from huginn.matchmaking.application.responses.batch_matchmaking_response import (
    BatchMatchmakingResponse,
)
from huginn.matchmaking.application.responses.user_failure import (
    UserFailure,
    UserFailureReason,
)
from huginn.matchmaking.application.services.matchmaking_service import (
    MatchmakingService,
    resolve_window,
)
from huginn.matchmaking.persistence.errors.database import (
    DatabaseOperationError,
    DatabaseUnavailableError,
)


class MatchmakingBatchService:
    def __init__(
        self,
        service: MatchmakingService,
        clock: Clock,
        readiness: Callable[[], None] | None = None,
    ) -> None:
        self._service = service
        self._clock = clock
        self._readiness = readiness

    def execute(self, request: BatchMatchmakingRequest) -> BatchMatchmakingResponse:
        if (
            not isinstance(request, BatchMatchmakingRequest)
            or not isinstance(request.user_ids, tuple)
            or not all(isinstance(id, UUID) for id in request.user_ids)
        ):
            raise InputValidationError("Invalid matchmaking User identifiers")
        window = resolve_window(request.cutoff, request.as_of, self._clock)
        user_ids = sorted(set(request.user_ids))
        if user_ids and self._readiness is not None:
            try:
                self._readiness()
            except (DatabaseOperationError, DatabaseUnavailableError) as exc:
                reason = (
                    UserFailureReason.DATABASE_UNAVAILABLE
                    if isinstance(exc, DatabaseUnavailableError)
                    else UserFailureReason.DATABASE_FAILURE
                )
                return BatchMatchmakingResponse(
                    window.cutoff,
                    window.as_of,
                    (),
                    tuple(UserFailure(id, reason) for id in user_ids),
                )
        responses = []
        failures = []
        for user_id in user_ids:
            try:
                responses.append(
                    self._service.execute(
                        MatchmakingRequest(user_id, window.cutoff, window.as_of)
                    )
                )
            except MatchmakingExecutionError as exc:
                failures.append(UserFailure(user_id, UserFailureReason(exc.reason)))
        return BatchMatchmakingResponse(
            window.cutoff, window.as_of, tuple(responses), tuple(failures)
        )
