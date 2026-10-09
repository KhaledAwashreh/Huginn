from collections.abc import Callable
from datetime import UTC, datetime
from uuid import uuid4

from huginn.pipeline_control.application.constants.execution_policy import (
    TRIGGER_HOURLY_LIMIT,
)
from huginn.pipeline_control.application.errors.trigger import TriggerRateLimitError
from huginn.pipeline_control.application.requests.trigger_invocation_request import (
    TriggerInvocationRequest,
)
from huginn.pipeline_control.application.responses.trigger_invocation_response import (
    TriggerInvocationResponse,
)
from huginn.pipeline_control.domain.entities.pipeline_invocation import (
    PipelineInvocation,
)
from huginn.pipeline_control.domain.errors.invocation import (
    ActiveInvocationConflictError,
)
from huginn.pipeline_control.domain.value_objects.invocation_state import (
    InvocationState,
)
from huginn.pipeline_control.domain.value_objects.pipeline_event import PipelineEvent
from huginn.pipeline_control.domain.value_objects.stage_plan import StagePlan
from huginn.pipeline_control.persistence.contracts.unit_of_work import (
    PipelineUnitOfWork,
)


class TriggerInvocationService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], PipelineUnitOfWork],
        plan: StagePlan,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._plan = plan
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(self, request: TriggerInvocationRequest) -> TriggerInvocationResponse:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("trigger clock must return a timezone-aware datetime")
        now = now.astimezone(UTC)
        try:
            with self._uow_factory() as uow:
                uow.invocations.lock_trigger_admission()
                existing = uow.invocations.get_by_request(
                    request.requester_account_id, request.request_id
                )
                if existing is not None:
                    uow.commit()
                    return _receipt(existing, created=False)
                retry_after = uow.throttle.reserve(
                    request.requester_account_id,
                    request.request_id,
                    now,
                    TRIGGER_HOURLY_LIMIT,
                )
                if retry_after is not None:
                    uow.rollback()
                    raise TriggerRateLimitError(retry_after)
                active = uow.invocations.active()
                if active is not None:
                    uow.commit()
                    raise ActiveInvocationConflictError(str(active.id))
                invocation = PipelineInvocation(
                    id=uuid4(),
                    requester_account_id=request.requester_account_id,
                    request_id=request.request_id,
                    state=InvocationState.QUEUED,
                    requested_at=now,
                    plan=self._plan,
                )
                uow.invocations.create(invocation)
                uow.events.append(
                    PipelineEvent(invocation.id, "invocation_queued", now),
                    "invocation_queued",
                )
                uow.commit()
                return _receipt(invocation, created=True)
        except TriggerRateLimitError, ActiveInvocationConflictError:
            raise
        except Exception:
            # The commit may have reached PostgreSQL even when the client lost
            # its acknowledgement. Request identity makes readback safe.
            with self._uow_factory() as read_uow:
                persisted = read_uow.invocations.get_by_request(
                    request.requester_account_id, request.request_id
                )
                if persisted is not None:
                    return _receipt(persisted, created=False)
            raise


def _receipt(
    invocation: PipelineInvocation, *, created: bool
) -> TriggerInvocationResponse:
    return TriggerInvocationResponse(
        id=invocation.id,
        status=invocation.state.value,
        requested_at=invocation.requested_at,
        created=created,
    )
