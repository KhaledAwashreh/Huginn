"""Persist an immutable target/window snapshot before acknowledging a trigger."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from huginn.matchmaking_control.application.requests.trigger_run_request import (
    TriggerRunRequest,
)
from huginn.matchmaking_control.application.responses.trigger_run_response import (
    TriggerRunResponse,
)
from huginn.matchmaking_control.domain.entities.matchmaking_run import MatchmakingRun
from huginn.matchmaking_control.domain.errors.run import (
    ActiveRunConflictError,
    NoEligibleUsersError,
    TargetUserDisabledError,
    TargetUserNotFoundError,
)
from huginn.matchmaking_control.persistence.contracts.unit_of_work import (
    MatchmakingControlUnitOfWork,
)

logger = logging.getLogger(__name__)


class Clock(Protocol):
    def now(self) -> datetime: ...


class TriggerRunService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], MatchmakingControlUnitOfWork],
        clock: Clock,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._clock = clock

    def execute(self, request: TriggerRunRequest) -> TriggerRunResponse:
        now = self._aware_utc(self._clock.now(), "current time")
        cutoff = self._aware_utc(request.cutoff, "cutoff")
        as_of = (
            now if request.as_of is None else self._aware_utc(request.as_of, "as_of")
        )
        if as_of > now:
            raise ValueError("as_of must not be in the future")
        if cutoff > as_of:
            raise ValueError("cutoff must not be after as_of")
        if request.target_kind not in ("user", "all_eligible"):
            raise ValueError("target kind must be user or all_eligible")
        if (request.target_kind == "user") != (request.user_id is not None):
            raise ValueError("user target requires exactly one user id")
        canonical: dict[str, object] = {
            "target_kind": request.target_kind,
            "user_id": str(request.user_id) if request.user_id is not None else None,
            "cutoff": cutoff.isoformat(),
            "as_of": None
            if request.as_of is None
            else self._aware_utc(request.as_of, "as_of").isoformat(),
        }
        logger.info("Admitting administrator matchmaking trigger")
        expected_error: (
            ActiveRunConflictError
            | NoEligibleUsersError
            | TargetUserDisabledError
            | TargetUserNotFoundError
            | None
        ) = None
        run: MatchmakingRun | None = None
        replayed = False
        with self._uow_factory() as uow:
            try:
                run, replayed = uow.runs.admit_run(
                    requester=request.requester,
                    request_id=request.request_id,
                    canonical_request=canonical,
                    target_kind=request.target_kind,
                    user_id=request.user_id,
                    cutoff=cutoff,
                    as_of=as_of,
                    requested_at=now,
                )
                uow.commit()
            except (
                ActiveRunConflictError,
                NoEligibleUsersError,
                TargetUserDisabledError,
                TargetUserNotFoundError,
            ) as error:
                # Distinct valid submissions count toward admission throttling.
                uow.commit()
                expected_error = error
        if expected_error is not None:
            raise expected_error
        assert run is not None
        return TriggerRunResponse(
            id=run.id,
            state=run.state,
            requested_at=run.requested_at,
            cutoff=run.cutoff,
            as_of=run.as_of,
            target_count=run.target_count,
            replayed=replayed,
        )

    @staticmethod
    def _aware_utc(value: datetime, name: str) -> datetime:
        if (
            not isinstance(value, datetime)
            or value.tzinfo is None
            or value.utcoffset() is None
        ):
            raise ValueError(f"{name} must be timezone-aware")
        return value.astimezone(UTC)
