from datetime import UTC, datetime
from uuid import UUID

from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.pipeline_control.domain.value_objects.execution_owner import ExecutionOwner
from huginn.pipeline_control.persistence.row_models.execution_guard import (
    ExecutionGuardRow,
)


class PostgresExecutionGuardRepository:
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def acquire(self, owner: ExecutionOwner) -> bool:
        row = self.connection.execute(
            "UPDATE ops.pipeline_execution_guard SET owner_id = %s, execution_id = %s, invocation_id = %s, "
            "host = %s, supervisor_pid = %s, supervisor_started_at = %s, executor_pid = NULL, "
            "executor_started_at = NULL, acquired_at = %s, released_at = NULL, active = TRUE, resource_kind = %s, matchmaking_run_id = %s "
            "WHERE singleton = 1 AND active = FALSE RETURNING singleton",
            (
                owner.owner_id,
                owner.execution_id,
                owner.invocation_id,
                owner.host,
                owner.supervisor_pid,
                owner.supervisor_started_at,
                datetime.now(UTC),
                owner.resource_kind,
                owner.matchmaking_run_id,
            ),
        ).fetchone()
        return row is not None

    def release(self, owner_id: UUID) -> bool:
        row = self.connection.execute(
            "UPDATE ops.pipeline_execution_guard SET active = FALSE, released_at = %s "
            "WHERE singleton = 1 AND active = TRUE AND owner_id = %s RETURNING singleton",
            (datetime.now(UTC), owner_id),
        ).fetchone()
        return row is not None

    def attach_executor(
        self, owner_id: UUID, executor_pid: int, executor_started_at: str
    ) -> bool:
        row = self.connection.execute(
            "UPDATE ops.pipeline_execution_guard SET executor_pid = %s, executor_started_at = %s "
            "WHERE singleton = 1 AND active = TRUE AND owner_id = %s RETURNING singleton",
            (executor_pid, executor_started_at, owner_id),
        ).fetchone()
        return row is not None

    def heartbeat(self, owner_id: UUID) -> bool:
        row = self.connection.execute(
            "UPDATE ops.pipeline_invocations AS i SET heartbeat_at = %s "
            "FROM ops.pipeline_execution_guard AS g "
            "WHERE g.singleton = 1 AND g.active = TRUE AND g.owner_id = %s "
            "AND i.id = g.invocation_id AND i.worker_id = %s RETURNING i.id",
            (datetime.now(UTC), owner_id, str(owner_id)),
        ).fetchone()
        if row is not None:
            return True
        row = self.connection.execute(
            "UPDATE ops.matchmaking_runs AS r SET heartbeat_at = %s "
            "FROM ops.pipeline_execution_guard AS g "
            "WHERE g.singleton = 1 AND g.active = TRUE AND g.owner_id = %s "
            "AND g.resource_kind = 'matchmaking' AND r.id = g.matchmaking_run_id "
            "AND r.worker_id = %s RETURNING r.id",
            (datetime.now(UTC), owner_id, str(owner_id)),
        ).fetchone()
        if row is not None:
            return True
        return (
            self.connection.execute(
                "SELECT 1 FROM ops.pipeline_execution_guard WHERE singleton = 1 AND active = TRUE AND owner_id = %s AND invocation_id IS NULL AND matchmaking_run_id IS NULL",
                (owner_id,),
            ).fetchone()
            is not None
        )

    def get_active(
        self,
    ) -> tuple[ExecutionOwner | None, int | None, str | None, bool] | None:
        row = self.connection.execute(
            "SELECT owner_id, execution_id, invocation_id, host, supervisor_pid, supervisor_started_at, "
            "executor_pid, executor_started_at, acquired_at, released_at, active, resource_kind, matchmaking_run_id "
            "FROM ops.pipeline_execution_guard WHERE singleton = 1"
        ).fetchone()
        return _guard_projection(row) if row is not None else None

    def inspect(
        self, execution_id: UUID
    ) -> tuple[ExecutionOwner | None, int | None, str | None, bool] | None:
        row = self.connection.execute(
            "SELECT owner_id, execution_id, invocation_id, host, supervisor_pid, supervisor_started_at, "
            "executor_pid, executor_started_at, acquired_at, released_at, active, resource_kind, matchmaking_run_id "
            "FROM ops.pipeline_execution_guard "
            "WHERE singleton = 1 AND active = TRUE AND execution_id = %s",
            (execution_id,),
        ).fetchone()
        if row is None:
            return None
        return _guard_projection(row)

    def inspect_invocation(
        self, invocation_id: UUID
    ) -> tuple[ExecutionOwner | None, int | None, str | None, bool] | None:
        row = self.connection.execute(
            "SELECT owner_id, execution_id, invocation_id, host, supervisor_pid, supervisor_started_at, "
            "executor_pid, executor_started_at, acquired_at, released_at, active, resource_kind, matchmaking_run_id "
            "FROM ops.pipeline_execution_guard "
            "WHERE singleton = 1 AND active = TRUE AND invocation_id = %s",
            (invocation_id,),
        ).fetchone()
        return _guard_projection(row) if row is not None else None


def _guard_row(row: tuple[object, ...]) -> ExecutionGuardRow:
    fields = (
        "owner_id",
        "execution_id",
        "invocation_id",
        "host",
        "supervisor_pid",
        "supervisor_started_at",
        "executor_pid",
        "executor_started_at",
        "acquired_at",
        "released_at",
        "active",
        "resource_kind",
        "matchmaking_run_id",
    )
    return ExecutionGuardRow.model_validate(
        dict(zip(fields if len(row) == 13 else fields[:11], row, strict=True))
    )


def _guard_projection(
    row: tuple[object, ...],
) -> tuple[ExecutionOwner | None, int | None, str | None, bool]:
    persisted = _guard_row(row)
    owner = None
    if persisted.owner_id is not None:
        if (
            persisted.execution_id is None
            or persisted.host is None
            or persisted.supervisor_pid is None
            or persisted.supervisor_started_at is None
        ):
            raise ValueError("invalid_execution_owner")
        owner = ExecutionOwner(
            persisted.owner_id,
            persisted.execution_id,
            persisted.invocation_id,
            persisted.host,
            persisted.supervisor_pid,
            persisted.supervisor_started_at,
            persisted.resource_kind,
            persisted.matchmaking_run_id,
        )
    return (
        owner,
        persisted.executor_pid,
        persisted.executor_started_at,
        persisted.active,
    )
