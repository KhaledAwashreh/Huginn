"""PostgreSQL session lock paired with the durable execution guard."""

import logging
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID

from huginn.management.persistence.contracts.database import (
    ConnectionFactory,
    DatabaseSession,
)
from huginn.pipeline_control.application.errors.execution import (
    ExecutionUnavailableError,
    TrackingUncertainError,
)
from huginn.pipeline_control.application.protocols.execution_guard import (
    ExecutionGuard,
)
from huginn.pipeline_control.application.read_models.executor_identity import (
    ExecutorIdentity,
)
from huginn.pipeline_control.domain.value_objects.execution_owner import ExecutionOwner
from huginn.pipeline_control.domain.value_objects.pipeline_event import PipelineEvent
from huginn.pipeline_control.persistence.repositories.execution_guard import (
    PostgresExecutionGuardRepository,
)
from huginn.pipeline_control.persistence.repositories.invocation import (
    PostgresInvocationRepository,
)
from huginn.pipeline_control.persistence.repositories.invocation_event import (
    PostgresInvocationEventRepository,
)

logger = logging.getLogger(__name__)

_EXECUTION_LOCK_KEYS = (1213548366, 2)
_STATEMENT_TIMEOUT_MS = 2_000


class PostgresExecutionGuard(ExecutionGuard):
    """Hold the shared session lock while updating its durable owner row."""

    def __init__(
        self, connection_factory: ConnectionFactory, *, resource_kind: str = "pipeline"
    ) -> None:
        if resource_kind not in {"pipeline", "matchmaking"}:
            raise ValueError("unsupported execution resource")
        self._resource_kind = resource_kind
        self._connection_factory = connection_factory
        self._connection: DatabaseSession | None = None
        self._owner: ExecutionOwner | None = None

    def acquire(self, owner: ExecutionOwner) -> bool:
        self._check_resource(owner)
        if self._connection is not None:
            raise ExecutionUnavailableError("execution_guard_already_open")
        connection: DatabaseSession | None = None
        try:
            connection = self._open_connection()
            self._set_statement_timeout(connection)
            row = connection.execute(
                "SELECT pg_try_advisory_lock(%s, %s)", _EXECUTION_LOCK_KEYS
            ).fetchone()
            connection.commit()
            if row is None or row[0] is not True:
                self._discard_connection(connection)
                logger.info("Shared execution lock is busy")
                return False

            claimed = PostgresExecutionGuardRepository(connection).acquire(owner)
            connection.commit()
            if not claimed:
                self._connection = connection
                self.close()
                return False

            self._connection, self._owner = connection, owner
            logger.info("Execution guard acquired for execution %s", owner.execution_id)
            return True
        except Exception as exc:
            if connection is not None:
                self._discard_connection(connection)
            logger.warning(
                "Execution guard acquisition failed (%s)", type(exc).__name__
            )
            raise ExecutionUnavailableError("execution_guard_unavailable") from None

    def attach_executor(self, owner_id: UUID, identity: ExecutorIdentity) -> None:
        connection, owner = self._require_owner(owner_id)
        if identity.host != owner.host or identity.pid <= 0 or not identity.started_at:
            raise TrackingUncertainError("executor_identity_invalid")
        try:
            self._require_session_lock(connection, owner_id)
            attached = PostgresExecutionGuardRepository(connection).attach_executor(
                owner_id, identity.pid, identity.started_at
            )
            if not attached:
                connection.rollback()
                raise TrackingUncertainError("execution_guard_owner_changed")
            connection.commit()
        except TrackingUncertainError:
            raise
        except Exception:
            self._rollback(connection)
            raise TrackingUncertainError("execution_guard_tracking_uncertain") from None

    def heartbeat(self, owner_id: UUID) -> None:
        connection, _ = self._require_owner(owner_id)
        try:
            self._require_session_lock(connection, owner_id)
            alive = PostgresExecutionGuardRepository(connection).heartbeat(owner_id)
            if not alive:
                connection.rollback()
                raise TrackingUncertainError("execution_guard_owner_changed")
            connection.commit()
        except TrackingUncertainError:
            raise
        except Exception:
            self._rollback(connection)
            raise TrackingUncertainError("execution_guard_heartbeat_failed") from None

    def release(self, owner_id: UUID) -> bool:
        connection, _ = self._require_owner(owner_id)
        try:
            self._require_session_lock(connection, owner_id)
            repository = PostgresExecutionGuardRepository(connection)
            active = repository.get_active()
            if (
                active is None
                or not active[3]
                or active[0] is None
                or active[0].owner_id != owner_id
            ):
                connection.rollback()
                return False
            released = repository.release(owner_id)
            if not released:
                connection.rollback()
                return False
            connection.commit()
        except Exception:
            self._rollback(connection)
            raise ExecutionUnavailableError("execution_guard_release_failed") from None

        self.close()
        logger.info("Execution guard released for owner %s", owner_id)
        return True

    def settle(
        self,
        owner: ExecutionOwner,
        state: str,
        safe_error_code: str | None = None,
    ) -> bool:
        """Finalize invocation history and clear its guard atomically."""
        self._check_resource(owner)
        if state not in {"succeeded", "failed", "interrupted", "completed_with_errors"}:
            raise ValueError("invalid terminal invocation state")
        connection, _ = self._require_owner(owner.owner_id)
        if self._owner != owner:
            raise TrackingUncertainError("execution_guard_owner_changed")
        try:
            self._require_session_lock(connection, owner.owner_id)
            guard_repository = PostgresExecutionGuardRepository(connection)
            if owner.invocation_id is not None:
                now = datetime.now(UTC)
                if not PostgresInvocationRepository(connection).finish(
                    owner.invocation_id,
                    str(owner.owner_id),
                    state,
                    now,
                    safe_error_code,
                ):
                    connection.rollback()
                    return False
                event_kind = {
                    "succeeded": "invocation_succeeded",
                    "failed": "invocation_failed",
                    "interrupted": "invocation_interrupted",
                }[state]
                PostgresInvocationEventRepository(connection).append(
                    PipelineEvent(
                        owner.invocation_id,
                        event_kind,
                        now,
                        safe_code=safe_error_code,
                        safe_message=f"Pipeline execution {state}",
                    ),
                    f"{event_kind}:{owner.execution_id}",
                )
            if owner.matchmaking_run_id is not None:
                from huginn.matchmaking_control.persistence.repositories.run_repository import (
                    PostgresRunRepository,
                )

                runs = PostgresRunRepository(connection)
                if state == "interrupted":
                    settled = runs.reconcile_run(
                        run_id=owner.matchmaking_run_id,
                        worker_id=owner.owner_id,
                        finished_at=datetime.now(UTC),
                    )
                else:
                    settled = runs.finish_run(
                        run_id=owner.matchmaking_run_id,
                        worker_id=owner.owner_id,
                        finished_at=datetime.now(UTC),
                    )
                if not settled:
                    connection.rollback()
                    return False
            if not guard_repository.release(owner.owner_id):
                connection.rollback()
                return False
            connection.commit()
        except Exception:
            self._rollback(connection)
            if self._settlement_visible(owner, state):
                self.close()
                logger.info(
                    "Execution settlement confirmed by readback for %s",
                    owner.execution_id,
                )
                return True
            self.close()
            logger.warning("Execution settlement uncertain for %s", owner.execution_id)
            return False

        self.close()
        logger.info("Execution %s settled as %s", owner.execution_id, state)
        return True

    def close(self) -> None:
        """Release only this connection's advisory lock, never durable state."""
        connection, self._connection = self._connection, None
        self._owner = None
        if connection is None:
            return
        try:
            connection.execute(
                "SELECT pg_advisory_unlock(%s, %s)", _EXECUTION_LOCK_KEYS
            ).fetchone()
            connection.commit()
        except Exception as exc:
            self._rollback(connection)
            logger.warning(
                "Advisory unlock failed (%s); closing lock connection",
                type(exc).__name__,
            )
        finally:
            with suppress(Exception):
                connection.close()

    def inspect(
        self, execution_id: UUID
    ) -> tuple[ExecutionOwner, ExecutorIdentity | None] | None:
        connection = self._open_connection()
        try:
            self._set_statement_timeout(connection)
            row = PostgresExecutionGuardRepository(connection).inspect(execution_id)
            connection.commit()
            return _owner_projection(row)
        except Exception:
            self._rollback(connection)
            raise ExecutionUnavailableError(
                "execution_guard_inspection_failed"
            ) from None
        finally:
            with suppress(Exception):
                connection.close()

    def inspect_invocation(
        self, invocation_id: UUID
    ) -> tuple[ExecutionOwner, ExecutorIdentity | None] | None:
        connection = self._open_connection()
        try:
            row = PostgresExecutionGuardRepository(connection).get_active()
            connection.commit()
            if (
                row is None
                or not row[3]
                or row[0] is None
                or row[0].invocation_id != invocation_id
            ):
                return None
            return _owner_projection(row)
        except Exception:
            self._rollback(connection)
            raise ExecutionUnavailableError(
                "execution_guard_inspection_failed"
            ) from None
        finally:
            with suppress(Exception):
                connection.close()

    def reconcile(self, owner: ExecutionOwner) -> bool:
        """Recover only the exact stopped owner while holding its resource lock.

        The caller must prove that the supervisor and executor have stopped
        before invoking this method. This adapter independently fences the
        matching durable owner and performs projection, event, and guard
        settlement in one transaction.
        """
        self._check_resource(owner)
        connection = self._open_connection()
        keep_connection = False
        try:
            self._set_statement_timeout(connection)
            locked = connection.execute(
                "SELECT pg_try_advisory_lock(%s, %s)", _EXECUTION_LOCK_KEYS
            ).fetchone()
            connection.commit()
            if locked is None or locked[0] is not True:
                return False

            guard_repository = PostgresExecutionGuardRepository(connection)
            persisted = guard_repository.inspect(owner.execution_id)
            if not _matches_owner(persisted, owner):
                connection.rollback()
                return False

            now = datetime.now(UTC)
            if owner.invocation_id is not None:
                reconciled = PostgresInvocationRepository(connection).reconcile(
                    owner.invocation_id, str(owner.owner_id), now
                )
                if not reconciled:
                    connection.rollback()
                    return False
                PostgresInvocationEventRepository(connection).append(
                    PipelineEvent(
                        owner.invocation_id,
                        "invocation_interrupted",
                        now,
                        safe_code="executor_interrupted",
                        safe_message="Stopped execution was reconciled",
                    ),
                    f"invocation_interrupted:reconcile:{owner.execution_id}",
                )
            if owner.matchmaking_run_id is not None:
                from huginn.matchmaking_control.persistence.repositories.run_repository import (
                    PostgresRunRepository,
                )

                if not PostgresRunRepository(connection).reconcile_run(
                    run_id=owner.matchmaking_run_id,
                    worker_id=owner.owner_id,
                    finished_at=now,
                ):
                    connection.rollback()
                    return False
            if not guard_repository.release(owner.owner_id):
                connection.rollback()
                return False
            connection.commit()
            keep_connection = True
            logger.info("Reconciled stopped execution %s", owner.execution_id)
            return True
        except Exception:
            self._rollback(connection)
            raise ExecutionUnavailableError(
                "execution_guard_reconciliation_failed"
            ) from None
        finally:
            if keep_connection:
                self._unlock_and_close(connection)
            else:
                self._discard_connection(connection)

    def _settlement_visible(self, owner: ExecutionOwner, state: str) -> bool:
        connection: DatabaseSession | None = None
        try:
            connection = self._open_connection()
            guard = PostgresExecutionGuardRepository(connection).get_active()
            invocation = (
                PostgresInvocationRepository(connection).get(owner.invocation_id)
                if owner.invocation_id is not None
                else None
            )
            matching_run = None
            if owner.matchmaking_run_id is not None:
                from huginn.matchmaking_control.persistence.repositories.run_repository import (
                    PostgresRunRepository,
                )

                matching_run = PostgresRunRepository(connection).get_run(
                    owner.matchmaking_run_id
                )
            connection.commit()
            return (
                (
                    owner.matchmaking_run_id is None
                    or (
                        matching_run is not None
                        and matching_run.state.value
                        in (
                            {"succeeded", "completed_with_errors"}
                            if state != "interrupted"
                            else {"interrupted"}
                        )
                    )
                )
                and guard is not None
                and not guard[3]
                and guard[0] == owner
                and (
                    owner.invocation_id is None
                    or (invocation is not None and invocation.state.value == state)
                )
            )
        except Exception:
            if connection is not None:
                self._rollback(connection)
            return False
        finally:
            if connection is not None:
                with suppress(Exception):
                    connection.close()

    def _check_resource(self, owner: ExecutionOwner) -> None:
        if owner.resource_kind != self._resource_kind:
            raise ExecutionUnavailableError("execution_resource_mismatch")

    def inspect_matchmaking_run(self, run_id: UUID):
        connection = self._open_connection()
        try:
            row = PostgresExecutionGuardRepository(connection).get_active()
            connection.commit()
            if (
                row is None
                or row[0] is None
                or row[0].resource_kind != "matchmaking"
                or row[0].matchmaking_run_id != run_id
            ):
                return None
            return _owner_projection(row)
        finally:
            connection.close()

    def _open_connection(self) -> DatabaseSession:
        connection = self._connection_factory.connect()
        try:
            self._set_statement_timeout(connection)
            return connection
        except Exception:
            with suppress(Exception):
                connection.close()
            raise

    @staticmethod
    def _set_statement_timeout(connection: DatabaseSession) -> None:
        with connection.cursor() as cursor:
            cursor.execute(f"SET statement_timeout = {_STATEMENT_TIMEOUT_MS}")
        connection.commit()

    def _require_owner(self, owner_id: UUID) -> tuple[DatabaseSession, ExecutionOwner]:
        connection, owner = self._connection, self._owner
        if connection is None or owner is None or owner.owner_id != owner_id:
            raise TrackingUncertainError("execution_guard_not_owned")
        return connection, owner

    @staticmethod
    def _require_session_lock(connection: DatabaseSession, owner_id: UUID) -> None:
        row = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_locks "
            "WHERE locktype = 'advisory' AND pid = pg_backend_pid() "
            "AND classid = %s::oid AND objid = %s::oid AND objsubid = 2 AND granted)",
            _EXECUTION_LOCK_KEYS,
        ).fetchone()
        if row is None or row[0] is not True:
            connection.rollback()
            raise TrackingUncertainError("execution_guard_session_lock_lost")
        active = PostgresExecutionGuardRepository(connection).get_active()
        if (
            active is None
            or not active[3]
            or active[0] is None
            or active[0].owner_id != owner_id
        ):
            connection.rollback()
            raise TrackingUncertainError("execution_guard_owner_changed")

    @staticmethod
    def _rollback(connection: DatabaseSession) -> None:
        with suppress(Exception):
            connection.rollback()

    def _discard_connection(self, connection: DatabaseSession) -> None:
        if self._connection is connection:
            self._connection = None
            self._owner = None
        self._unlock_and_close(connection)

    def _unlock_and_close(self, connection: DatabaseSession) -> None:
        try:
            connection.execute(
                "SELECT pg_advisory_unlock(%s, %s)", _EXECUTION_LOCK_KEYS
            ).fetchone()
            connection.commit()
        except Exception as exc:
            self._rollback(connection)
            logger.warning(
                "Advisory unlock failed (%s); closing lock connection",
                type(exc).__name__,
            )
        finally:
            with suppress(Exception):
                connection.close()


def _owner_projection(
    row: tuple[ExecutionOwner | None, int | None, str | None, bool] | None,
) -> tuple[ExecutionOwner, ExecutorIdentity | None] | None:
    if row is None or not row[3] or row[0] is None:
        return None
    owner, pid, started_at, _ = row
    executor = (
        ExecutorIdentity(owner.host, pid, started_at)
        if pid is not None and started_at is not None
        else None
    )
    return owner, executor


def _matches_owner(
    row: tuple[ExecutionOwner | None, int | None, str | None, bool] | None,
    owner: ExecutionOwner,
) -> bool:
    return row is not None and row[3] and row[0] == owner
