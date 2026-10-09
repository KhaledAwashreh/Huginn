"""Short queue claim, durable admission, then trusted supervised work."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from huginn.pipeline_control.application.errors.execution import (
    ExecutorTerminationUnprovenError,
)
from huginn.pipeline_control.application.protocols.execution_guard import ExecutionGuard
from huginn.pipeline_control.application.protocols.executor_supervisor import (
    ExecutorSupervisor,
)
from huginn.pipeline_control.application.requests.run_queued_invocation_request import (
    RunQueuedInvocationRequest,
)
from huginn.pipeline_control.application.responses.run_queued_invocation_response import (
    RunQueuedInvocationResponse,
)
from huginn.pipeline_control.domain.value_objects.execution_owner import ExecutionOwner
from huginn.pipeline_control.domain.value_objects.pipeline_event import PipelineEvent
from huginn.pipeline_control.persistence.contracts.unit_of_work import (
    PipelineUnitOfWork,
)


class RunQueuedInvocationService:
    def __init__(
        self,
        uow_factory: Callable[[], PipelineUnitOfWork],
        guard_factory: Callable[[], ExecutionGuard],
        supervisor: ExecutorSupervisor,
        owner_factory: Callable[[UUID | None], ExecutionOwner],
    ) -> None:
        self._uow_factory = uow_factory
        self._guard_factory = guard_factory
        self._supervisor = supervisor
        self._owner_factory = owner_factory

    def execute(
        self, request: RunQueuedInvocationRequest
    ) -> RunQueuedInvocationResponse:
        guard = self._guard_factory()
        owner = self._owner_factory(None)
        try:
            with self._uow_factory() as uow:
                invocation = uow.invocations.claim_queued(
                    str(owner.owner_id), datetime.now(UTC)
                )
                if invocation is None:
                    return RunQueuedInvocationResponse(None, "idle")
                owner = replace(owner, invocation_id=invocation.id)
                if not guard.acquire(owner):
                    return RunQueuedInvocationResponse(invocation.id, "waiting")
                now = datetime.now(UTC)
                if not uow.invocations.mark_running(
                    invocation.id, str(owner.owner_id), now
                ):
                    raise RuntimeError("claim_unavailable")
                uow.events.append(
                    PipelineEvent(
                        invocation.id,
                        "invocation_started",
                        now,
                        safe_message="Pipeline execution started.",
                    ),
                    "invocation_started",
                )
                uow.commit()
            try:
                outcome = self._supervisor.run(owner, guard)
                state = (
                    "succeeded"
                    if outcome == 0
                    else ("interrupted" if outcome == 3 else "failed")
                )
                code = (
                    None
                    if outcome == 0
                    else (
                        "tracking_unavailable" if outcome == 3 else "execution_failed"
                    )
                )
            except ExecutorTerminationUnprovenError:
                raise
            except BaseException:
                state, code = "interrupted", "execution_interrupted"
                if not guard.settle(owner, state, code):
                    raise RuntimeError("settlement_unavailable") from None
                return RunQueuedInvocationResponse(invocation.id, state)
            if not guard.settle(owner, state, code):
                raise RuntimeError("settlement_unavailable")
            return RunQueuedInvocationResponse(invocation.id, state)
        finally:
            guard.close()
