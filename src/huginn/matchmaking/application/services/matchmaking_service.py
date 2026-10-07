"""Creation-only per-User orchestration, matchmaking design section 8."""

import logging
import time
from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from huginn.matchmaking.application.constants.retries import MAX_ATTEMPTS, RETRY_DELAYS
from huginn.matchmaking.application.errors.execution import (
    CommitOutcomeUnknownExecutionError,
    DatabaseFailureExecutionError,
    DatabaseUnavailableExecutionError,
    InputValidationError,
    RetriesExhaustedExecutionError,
)
from huginn.matchmaking.application.protocols.clock import Clock
from huginn.matchmaking.application.read_models.company_candidate import (
    CompanyCandidate,
)
from huginn.matchmaking.application.read_models.user_availability import (
    UserAvailability,
)
from huginn.matchmaking.application.requests.matchmaking_request import (
    MatchmakingRequest,
)
from huginn.matchmaking.application.responses.matchmaking_response import (
    MatchmakingResponse,
    MatchmakingStatus,
)
from huginn.matchmaking.application.responses.skipped_strategy import SkippedStrategy
from huginn.matchmaking.domain.errors.criteria import CriteriaIssue
from huginn.matchmaking.domain.services.icp_evaluator import compile_icp
from huginn.matchmaking.domain.value_objects.compiled_criteria import CompiledCriteria
from huginn.matchmaking.domain.value_objects.signal_window import SignalWindow
from huginn.matchmaking.persistence.errors.database import (
    CommitOutcomeUnknownError,
    DatabaseOperationError,
    DatabaseUnavailableError,
    RetryableTransactionError,
)
from huginn.matchmaking.persistence.unit_of_work.protocol import MatchmakingUnitOfWork

logger = logging.getLogger(__name__)


def resolve_window(
    cutoff: datetime, as_of: datetime | None, clock: Clock
) -> SignalWindow:
    if not isinstance(cutoff, datetime) or (
        as_of is not None and not isinstance(as_of, datetime)
    ):
        raise InputValidationError("Invalid matchmaking time window")
    try:
        return SignalWindow(cutoff, clock.now() if as_of is None else as_of)
    except (ValueError, TypeError) as exc:
        raise InputValidationError("Invalid matchmaking time window") from exc


class MatchmakingService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], MatchmakingUnitOfWork],
        clock: Clock,
        retry_delay: Callable[[float], None] = time.sleep,
    ) -> None:
        self._factory = unit_of_work_factory
        self._clock = clock
        self._retry_delay = retry_delay

    def execute(self, request: MatchmakingRequest) -> MatchmakingResponse:
        if not isinstance(request, MatchmakingRequest) or not isinstance(
            request.user_id, UUID
        ):
            raise InputValidationError("Invalid matchmaking User identifier")
        window = resolve_window(request.cutoff, request.as_of, self._clock)
        logger.info("Matchmaking execution started")
        for attempt in range(MAX_ATTEMPTS):
            try:
                return self._attempt(request.user_id, window)
            except RetryableTransactionError as exc:
                if attempt == MAX_ATTEMPTS - 1:
                    raise RetriesExhaustedExecutionError(
                        "Matchmaking retries exhausted"
                    ) from exc
                self._retry_delay(RETRY_DELAYS[attempt])
            except CommitOutcomeUnknownError as exc:
                raise CommitOutcomeUnknownExecutionError(
                    "Matchmaking commit outcome unknown"
                ) from exc
            except DatabaseUnavailableError as exc:
                raise DatabaseUnavailableExecutionError(
                    "Matchmaking database unavailable"
                ) from exc
            except DatabaseOperationError as exc:
                raise DatabaseFailureExecutionError(
                    "Matchmaking database operation failed"
                ) from exc
        raise AssertionError("Unreachable retry state")

    def _attempt(self, user_id: UUID, window: SignalWindow) -> MatchmakingResponse:
        with self._factory() as uow:
            availability = uow.configuration.user_availability(user_id)
            if availability != UserAvailability.ACTIVE:
                status = (
                    MatchmakingStatus.DISABLED_USER
                    if availability == UserAvailability.DISABLED
                    else MatchmakingStatus.USER_NOT_FOUND
                )
                return MatchmakingResponse(
                    user_id, status, window.cutoff, window.as_of, 0, 0, 0, (), 0, ()
                )
            configurations = uow.configuration.list_active_strategies(user_id)
            memo: dict[CompiledCriteria, tuple[CompanyCandidate, ...]] = {}
            skipped = []
            company_ids: set[UUID] = set()
            for configuration in configurations:
                criteria = compile_icp(
                    industries=configuration.industries,
                    company_sizes=configuration.company_sizes,
                    geographies=configuration.geographies,
                    exclusions=configuration.exclusions,
                )
                if isinstance(criteria, CriteriaIssue):
                    skipped.append(
                        SkippedStrategy(configuration.strategy_id, criteria.reason)
                    )
                    continue
                if criteria not in memo:
                    memo[criteria] = uow.candidates.find_candidates(criteria, window)
                company_ids.update(candidate.company_id for candidate in memo[criteria])
            created = []
            existing = 0
            for company_id in sorted(company_ids):
                match = uow.matches.insert_if_absent(user_id, company_id)
                if match is None:
                    existing += 1
                else:
                    created.append(match)
            uow.commit()
        logger.info("Matchmaking execution committed")
        return MatchmakingResponse(
            user_id,
            MatchmakingStatus.SUCCEEDED,
            window.cutoff,
            window.as_of,
            len(configurations),
            len(skipped),
            len(company_ids),
            tuple(created),
            existing,
            tuple(sorted(skipped, key=lambda item: item.strategy_id)),
        )
