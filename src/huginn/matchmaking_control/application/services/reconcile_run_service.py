"""Explicit stopped-owner reconciliation without replay."""

from huginn.matchmaking_control.application.requests.reconcile_run_request import (
    ReconcileRunRequest,
)
from huginn.matchmaking_control.application.responses.reconcile_run_response import (
    ReconcileRunResponse,
)
from huginn.pipeline_control.application.errors.execution import (
    ExecutionUnavailableError,
)


class ReconcileRunService:
    def __init__(self, guard, supervisor):
        self._guard, self._supervisor = guard, supervisor

    def execute(self, request: ReconcileRunRequest) -> ReconcileRunResponse:
        if not request.executor_stopped:
            raise ExecutionUnavailableError("stopped_evidence_required")
        identity = self._guard.inspect_matchmaking_run(request.run_id)
        if identity is None:
            raise ExecutionUnavailableError("execution_not_found")
        owner, executor = identity
        if owner.resource_kind != "matchmaking":
            raise ExecutionUnavailableError("execution_resource_mismatch")
        if not self._supervisor.prove_stopped(owner, executor):
            raise ExecutionUnavailableError("executor_stop_unproven")
        if not self._guard.reconcile(owner):
            raise ExecutionUnavailableError("reconciliation_unavailable")
        return ReconcileRunResponse(request.run_id, True)
