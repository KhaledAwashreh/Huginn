"""Explicit stopped-owner reconciliation without replay."""

from huginn.matchmaking_control.application.requests.reconcile_execution_request import (
    ReconcileExecutionRequest,
)
from huginn.matchmaking_control.application.responses.reconcile_execution_response import (
    ReconcileExecutionResponse,
)
from huginn.pipeline_control.application.errors.execution import (
    ExecutionUnavailableError,
)


class ReconcileExecutionService:
    def __init__(self, guard, supervisor):
        self._guard, self._supervisor = guard, supervisor

    def execute(self, request: ReconcileExecutionRequest) -> ReconcileExecutionResponse:
        if not request.executor_stopped:
            raise ExecutionUnavailableError("stopped_evidence_required")
        identity = self._guard.inspect(request.execution_id)
        if identity is None:
            raise ExecutionUnavailableError("execution_not_found")
        owner, executor = identity
        if owner.resource_kind != "matchmaking":
            raise ExecutionUnavailableError("execution_resource_mismatch")
        if not self._supervisor.prove_stopped(owner, executor):
            raise ExecutionUnavailableError("executor_stop_unproven")
        if not self._guard.reconcile(owner):
            raise ExecutionUnavailableError("reconciliation_unavailable")
        return ReconcileExecutionResponse(request.execution_id, True)
