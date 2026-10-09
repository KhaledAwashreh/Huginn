"""Explicit recovery requires evidence about the exact stopped process identity."""

from huginn.pipeline_control.application.errors.execution import (
    ExecutionUnavailableError,
)
from huginn.pipeline_control.application.protocols.execution_guard import ExecutionGuard
from huginn.pipeline_control.application.protocols.executor_supervisor import (
    ExecutorSupervisor,
)
from huginn.pipeline_control.application.requests.reconcile_invocation_request import (
    ReconcileInvocationRequest,
)
from huginn.pipeline_control.application.responses.reconcile_invocation_response import (
    ReconcileInvocationResponse,
)


class ReconcileInvocationService:
    def __init__(self, guard: ExecutionGuard, supervisor: ExecutorSupervisor) -> None:
        self._guard = guard
        self._supervisor = supervisor

    def execute(
        self, request: ReconcileInvocationRequest
    ) -> ReconcileInvocationResponse:
        if not request.executor_stopped:
            raise ExecutionUnavailableError("stopped_evidence_required")
        identity = self._guard.inspect_invocation(request.invocation_id)
        if identity is None:
            raise ExecutionUnavailableError("execution_not_found")
        owner, executor = identity
        if owner.resource_kind != "pipeline":
            raise ExecutionUnavailableError("execution_resource_mismatch")
        if not self._supervisor.prove_stopped(owner, executor):
            raise ExecutionUnavailableError("executor_stop_unproven")
        if not self._guard.reconcile(owner):
            raise ExecutionUnavailableError("reconciliation_unavailable")
        return ReconcileInvocationResponse(request.invocation_id, "interrupted")
