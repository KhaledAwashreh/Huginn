from datetime import datetime
from typing import Any
from uuid import UUID

from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.pipeline_control.domain.entities.pipeline_invocation import (
    PipelineInvocation,
)
from huginn.pipeline_control.domain.value_objects.invocation_state import (
    InvocationState,
)
from huginn.pipeline_control.domain.value_objects.stage_plan import StagePlan
from huginn.pipeline_control.persistence.row_models.invocation import InvocationRow

_COLUMNS = "id, requester_account_id, request_id, state, requested_at, plan, started_at, finished_at, worker_id, heartbeat_at, safe_error_code, company_results_tracking_state"


class PostgresInvocationRepository:
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def lock_trigger_admission(self) -> None:
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)", (1213548366, 1)
        ).fetchone()

    def get_by_request(
        self, requester_account_id: UUID, request_id: UUID
    ) -> PipelineInvocation | None:
        return self._get(
            f"SELECT {_COLUMNS} FROM ops.pipeline_invocations WHERE requester_account_id = %s AND request_id = %s",
            (requester_account_id, request_id),
        )

    def get(self, invocation_id: UUID) -> PipelineInvocation | None:
        return self._get(
            f"SELECT {_COLUMNS} FROM ops.pipeline_invocations WHERE id = %s",
            (invocation_id,),
        )

    def active(self) -> PipelineInvocation | None:
        return self._get(
            f"SELECT {_COLUMNS} FROM ops.pipeline_invocations WHERE state IN ('queued', 'running')"
        )

    def create(self, invocation: PipelineInvocation) -> None:
        self.connection.execute(
            "INSERT INTO ops.pipeline_invocations (id, requester_account_id, request_id, state, requested_at, plan, company_results_tracking_state) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                invocation.id,
                invocation.requester_account_id,
                invocation.request_id,
                invocation.state.value,
                invocation.requested_at,
                JsonParameter(invocation.plan.to_json()),
                invocation.company_results_tracking_state,
            ),
        )

    def claim_queued(self, worker_id: str, now: datetime) -> PipelineInvocation | None:
        row = self.connection.execute(
            f"SELECT {_COLUMNS} FROM ops.pipeline_invocations "
            "WHERE state = 'queued' ORDER BY requested_at ASC, id ASC LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED"
        ).fetchone()
        if row is None:
            return None
        invocation = _invocation(row)
        self.connection.execute(
            "UPDATE ops.pipeline_invocations SET worker_id = %s WHERE id = %s AND state = 'queued'",
            (worker_id, invocation.id),
        )
        return invocation

    def mark_running(self, invocation_id: UUID, worker_id: str, now: datetime) -> bool:
        row = self.connection.execute(
            "UPDATE ops.pipeline_invocations SET state = 'running', worker_id = %s, started_at = %s, heartbeat_at = %s "
            "WHERE id = %s AND state = 'queued' AND worker_id = %s RETURNING id",
            (worker_id, now, now, invocation_id, worker_id),
        ).fetchone()
        return row is not None

    def heartbeat(self, invocation_id: UUID, worker_id: str, now: datetime) -> bool:
        row = self.connection.execute(
            "UPDATE ops.pipeline_invocations SET heartbeat_at = %s "
            "WHERE id = %s AND state = 'running' AND worker_id = %s RETURNING id",
            (now, invocation_id, worker_id),
        ).fetchone()
        return row is not None

    def finish(
        self,
        invocation_id: UUID,
        worker_id: str,
        state: str,
        finished_at: datetime,
        safe_error_code: str | None = None,
    ) -> bool:
        if state not in {"succeeded", "failed", "interrupted"}:
            raise ValueError("invalid terminal invocation state")
        row = self.connection.execute(
            "UPDATE ops.pipeline_invocations SET state = %s, finished_at = %s, safe_error_code = %s "
            "WHERE id = %s AND state = 'running' AND worker_id = %s RETURNING id",
            (state, finished_at, safe_error_code, invocation_id, worker_id),
        ).fetchone()
        return row is not None

    def reconcile(
        self, invocation_id: UUID, owner_id: str, finished_at: datetime
    ) -> bool:
        row = self.connection.execute(
            "UPDATE ops.pipeline_invocations SET state = 'interrupted', finished_at = %s, safe_error_code = 'executor_interrupted' "
            "WHERE id = %s AND ((state = 'running' AND worker_id = %s) "
            "OR (state = 'queued' AND started_at IS NULL)) "
            "AND EXISTS (SELECT 1 FROM ops.pipeline_execution_guard g "
            "WHERE g.active AND g.owner_id = %s::uuid AND g.invocation_id = ops.pipeline_invocations.id) RETURNING id",
            (finished_at, invocation_id, owner_id, owner_id),
        ).fetchone()
        return row is not None

    def _get(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> PipelineInvocation | None:
        row = self.connection.execute(query, params).fetchone()
        if row is None:
            return None
        return _invocation(row)


def _invocation(row: tuple[Any, ...]) -> PipelineInvocation:
    names = (
        "id",
        "requester_account_id",
        "request_id",
        "state",
        "requested_at",
        "plan",
        "started_at",
        "finished_at",
        "worker_id",
        "heartbeat_at",
        "safe_error_code",
        "company_results_tracking_state",
    )
    persisted = InvocationRow.model_validate(dict(zip(names, row, strict=True)))
    return PipelineInvocation(
        id=persisted.id,
        requester_account_id=persisted.requester_account_id,
        request_id=persisted.request_id,
        state=InvocationState(persisted.state),
        requested_at=persisted.requested_at,
        plan=StagePlan.from_json(persisted.plan),
        started_at=persisted.started_at,
        finished_at=persisted.finished_at,
        worker_id=persisted.worker_id,
        heartbeat_at=persisted.heartbeat_at,
        safe_error_code=persisted.safe_error_code,
        company_results_tracking_state=persisted.company_results_tracking_state,
    )
