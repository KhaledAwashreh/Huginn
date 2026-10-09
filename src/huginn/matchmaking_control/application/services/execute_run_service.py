"""Serial fixed-target evaluation with durable start and result acknowledgements."""

import logging
from dataclasses import replace
from datetime import UTC, datetime

from huginn.matchmaking_control.application.errors.execution import (
    ResultTrackingUncertainError,
)
from huginn.matchmaking_control.application.requests.execute_run_request import (
    ExecuteRunRequest,
)
from huginn.matchmaking_control.application.responses.execute_run_response import (
    ExecuteRunResponse,
)
from huginn.matchmaking_control.domain.value_objects.run_state import RunState

logger = logging.getLogger(__name__)


class ExecuteRunService:
    def __init__(self, unit_of_work_factory, executor, *, clock=None):
        self._factory = unit_of_work_factory
        self._executor = executor
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(self, request: ExecuteRunRequest) -> ExecuteRunResponse:
        with self._factory() as uow:
            run = uow.runs.get_run_snapshot(request.run_id)
            if (
                run is None
                or run.state != RunState.RUNNING
                or run.worker_id != str(request.worker_id)
            ):
                raise ResultTrackingUncertainError("run_not_owned")
            targets = uow.runs.pending_targets(request.run_id, request.worker_id)
        for target in targets:
            started = self._clock()
            try:
                with self._factory() as uow:
                    if not uow.runs.start_target(
                        run.id, target.user_id, request.worker_id, started
                    ):
                        raise ResultTrackingUncertainError("target_start_unavailable")
                    uow.commit()
            except Exception:
                # No matcher call has occurred. Preserve state for explicit recovery.
                raise ResultTrackingUncertainError("target_start_uncertain") from None
            logger.info("Managed matching target started: %s", target.user_id)
            result, skipped = self._executor.execute(
                target.user_id, run.cutoff, run.as_of
            )
            finished = self._clock()
            result = replace(
                result,
                run_id=run.id,
                ordinal=target.ordinal,
                started_at=started,
                finished_at=finished,
            )
            try:
                with self._factory() as uow:
                    if not uow.runs.acknowledge_target(
                        result, skipped, request.worker_id, finished
                    ):
                        raise ResultTrackingUncertainError(
                            "target_acknowledgement_unavailable"
                        )
                    uow.commit()
            except Exception:
                # A lost journal receipt may be resolved by a read, never a matcher replay.
                try:
                    with self._factory() as uow:
                        recorded = uow.runs.get_target(run.id, target.user_id)
                        current = uow.runs.get_run_snapshot(run.id)
                    acknowledged = (
                        recorded == result
                        and current is not None
                        and current.worker_id == str(request.worker_id)
                    )
                except Exception:
                    acknowledged = False
                if not acknowledged:
                    raise ResultTrackingUncertainError(
                        "result_tracking_uncertain"
                    ) from None
            logger.info("Managed matching target acknowledged: %s", target.user_id)
        return ExecuteRunResponse(run.id, "evaluated")
