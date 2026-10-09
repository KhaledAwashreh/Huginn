from datetime import UTC, datetime
from uuid import uuid4

from huginn.pipeline_control.application.read_models.executor_identity import (
    ExecutorIdentity,
)
from huginn.pipeline_control.domain.value_objects.execution_owner import ExecutionOwner
from huginn.pipeline_control.infrastructure.postgres_execution_guard import (
    PostgresExecutionGuard,
)


class Result:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class Session:
    def __init__(self, *, lock=True, guard=True):
        self.lock = lock
        self.guard = guard
        self.queries = []
        self.commits = 0
        self.closed = False
        self.active_owner = None
        self.active = False

    class _Cursor:
        def __init__(self, session):
            self.session = session

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, query, params=()):
            self.session.queries.append((query, params))

    def execute(self, query, params=()):
        self.queries.append((query, params))
        if "pg_try_advisory_lock" in query:
            return Result((self.lock,))
        if "pg_advisory_unlock" in query:
            return Result((True,))
        if "pg_locks" in query:
            return Result((self.lock,))
        if "UPDATE ops.pipeline_execution_guard SET owner_id" in query:
            self.active_owner = params[0]
            self.active_execution_id = params[1]
            self.active_invocation_id = params[2]
            self.active_host = params[3]
            self.active_supervisor_pid = params[4]
            self.active_supervisor_started_at = params[5]
            self.active = self.guard
            return Result((1,) if self.guard else None)
        if "UPDATE ops.pipeline_execution_guard SET active = FALSE" in query:
            self.active = False
            return Result((1,))
        if "UPDATE ops.pipeline_execution_guard SET executor_pid" in query:
            return Result((1,))
        if "UPDATE ops.pipeline_invocations AS i" in query:
            return Result((1,))
        if "FROM ops.pipeline_execution_guard" in query:
            return Result(self.guard_row())
        return Result(None)

    def cursor(self):
        return self._Cursor(self)

    def guard_row(self):
        return (
            self.active_owner,
            self.active_execution_id,
            self.active_invocation_id,
            self.active_host,
            self.active_supervisor_pid,
            self.active_supervisor_started_at,
            None,
            None,
            datetime.now(UTC),
            None,
            self.active,
        )

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def close(self):
        self.closed = True


class Factory:
    def __init__(self, session):
        self.session = session

    def connect(self):
        return self.session


def owner(*, invocation_id=None):
    return ExecutionOwner(uuid4(), uuid4(), invocation_id, "host-a", 101, "start-a")


def test_acquire_takes_session_lock_before_committing_durable_owner():
    session = Session()
    guard = PostgresExecutionGuard(Factory(session))

    assert guard.acquire(owner()) is True
    query_text = [query for query, _ in session.queries]
    lock_index = next(
        i for i, query in enumerate(query_text) if "pg_try_advisory_lock" in query
    )
    owner_index = next(
        i
        for i, query in enumerate(query_text)
        if "UPDATE ops.pipeline_execution_guard SET owner_id" in query
    )
    assert lock_index < owner_index
    assert session.commits >= 2


def test_busy_session_lock_closes_connection_without_claiming_durable_guard():
    session = Session(lock=False)
    guard = PostgresExecutionGuard(Factory(session))

    assert guard.acquire(owner()) is False
    assert session.closed
    assert not any(
        "UPDATE ops.pipeline_execution_guard SET owner_id" in q
        for q, _ in session.queries
    )


def test_close_releases_only_session_lock_and_preserves_durable_blocker():
    session = Session()
    guard = PostgresExecutionGuard(Factory(session))
    assert guard.acquire(owner())

    guard.close()

    queries = [query for query, _ in session.queries]
    assert any("pg_advisory_unlock" in query for query in queries)
    assert not any("SET active = FALSE" in query for query in queries)
    assert session.closed


def test_live_guard_attaches_executor_and_heartbeats_only_while_lock_is_owned():
    invocation_id = uuid4()
    session = Session()
    guard = PostgresExecutionGuard(Factory(session))
    current_owner = owner(invocation_id=invocation_id)
    assert guard.acquire(current_owner)
    identity = ExecutorIdentity("host-a", 202, "child-start")

    guard.attach_executor(current_owner.owner_id, identity)
    guard.heartbeat(current_owner.owner_id)

    assert any("pg_locks" in query for query, _ in session.queries)
    attached = next(
        params for query, params in session.queries if "SET executor_pid" in query
    )
    assert attached == (identity.pid, identity.started_at, current_owner.owner_id)
    assert any(
        "UPDATE ops.pipeline_invocations AS i" in query for query, _ in session.queries
    )


def test_lost_session_lock_makes_heartbeat_uncertain():
    import pytest

    from huginn.pipeline_control.application.errors.execution import (
        TrackingUncertainError,
    )

    session = Session()
    guard = PostgresExecutionGuard(Factory(session))
    current_owner = owner()
    assert guard.acquire(current_owner)
    session.lock = False

    with pytest.raises(TrackingUncertainError):
        guard.heartbeat(current_owner.owner_id)


def test_standalone_settlement_clears_guard_before_releasing_session_lock():
    session = Session()
    guard = PostgresExecutionGuard(Factory(session))
    current_owner = owner()
    assert guard.acquire(current_owner)

    assert guard.settle(current_owner, "succeeded")

    release_index = next(
        i
        for i, (query, _) in enumerate(session.queries)
        if "SET active = FALSE" in query
    )
    unlock_index = next(
        i
        for i, (query, _) in enumerate(session.queries)
        if "pg_advisory_unlock" in query
    )
    assert release_index < unlock_index
    assert session.closed


def test_inspect_invocation_projects_active_owner_without_pipeline_assumptions():
    session = Session()
    guard = PostgresExecutionGuard(Factory(session))
    current_owner = owner()
    assert current_owner.invocation_id is None
    assert guard.acquire(current_owner)
    guard.close()

    inspected = guard.inspect(current_owner.execution_id)

    assert inspected is not None
    assert inspected[0] == current_owner
    assert inspected[1] is None


def test_reconcile_requires_exact_durable_owner_and_releases_atomically():
    session = Session()
    guard = PostgresExecutionGuard(Factory(session))
    current_owner = owner()
    assert guard.acquire(current_owner)
    guard.close()

    assert guard.reconcile(current_owner)

    assert session.active is False
    assert session.closed


def test_live_postgres_guard_serializes_owners_and_keeps_close_separate_from_release(
    integration_database_url,
):
    import psycopg

    from huginn.management.persistence.database.client import (
        ManagementConnectionFactory,
    )
    from huginn.pipeline_control.persistence.repositories.execution_guard import (
        PostgresExecutionGuardRepository,
    )

    factory = ManagementConnectionFactory(integration_database_url)
    first, competing = PostgresExecutionGuard(factory), PostgresExecutionGuard(factory)
    account_id, invocation_id = uuid4(), uuid4()
    active_owner = owner(invocation_id=invocation_id)
    competing_owner = owner()
    try:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "INSERT INTO operational.accounts (id, username, password_hash) "
                "VALUES (%s, %s, %s)",
                (account_id, f"guard-{uuid4().hex}", "placeholder-hash"),
            )
            connection.execute(
                "INSERT INTO ops.pipeline_invocations "
                "(id, requester_account_id, request_id, state, requested_at, plan, worker_id) "
                "VALUES (%s, %s, %s, 'running', %s, '[]'::jsonb, %s)",
                (
                    invocation_id,
                    account_id,
                    uuid4(),
                    datetime.now(UTC),
                    str(active_owner.owner_id),
                ),
            )
        assert first.acquire(active_owner)
        assert not competing.acquire(competing_owner)
        first.attach_executor(
            active_owner.owner_id, ExecutorIdentity("host-a", 202, "child-start")
        )
        first.heartbeat(active_owner.owner_id)
        inspection = factory.connect()
        try:
            row = PostgresExecutionGuardRepository(inspection).get_active()
            assert row is not None and row[0] == active_owner and row[3]
        finally:
            inspection.close()
        with psycopg.connect(integration_database_url) as connection:
            heartbeat = connection.execute(
                "SELECT heartbeat_at FROM ops.pipeline_invocations WHERE id = %s",
                (invocation_id,),
            ).fetchone()[0]
            assert heartbeat is not None
    finally:
        first.close()
        competing.close()
        after_close = PostgresExecutionGuard(factory)
        assert not after_close.acquire(competing_owner)
        after_close.close()
        # `close` must leave durable recovery state active. Clean up only this
        # test's uniquely owned row after asserting that state below.
        cleanup = factory.connect()
        try:
            repository = PostgresExecutionGuardRepository(cleanup)
            row = repository.get_active()
            assert row is not None and row[0] == active_owner and row[3]
            assert repository.release(active_owner.owner_id)
            cleanup.commit()
        finally:
            cleanup.close()
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM ops.pipeline_invocation_events WHERE invocation_id = %s",
                (invocation_id,),
            )
            connection.execute(
                "UPDATE ops.pipeline_execution_guard SET invocation_id = NULL "
                "WHERE singleton = 1 AND active = FALSE AND invocation_id = %s",
                (invocation_id,),
            )
            connection.execute(
                "DELETE FROM ops.pipeline_invocations WHERE id = %s", (invocation_id,)
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s", (account_id,)
            )


def test_fixed_resource_dispatch_refuses_matching_owner_in_pipeline_guard():
    from dataclasses import replace

    import pytest

    from huginn.pipeline_control.application.errors.execution import (
        ExecutionUnavailableError,
    )

    current_owner = replace(owner(), resource_kind="matchmaking")
    guard = PostgresExecutionGuard(Factory(Session()))
    with pytest.raises(ExecutionUnavailableError, match="execution_resource_mismatch"):
        guard.acquire(current_owner)


def test_matching_guard_refuses_pipeline_recovery():
    from dataclasses import replace

    import pytest

    from huginn.pipeline_control.application.errors.execution import (
        ExecutionUnavailableError,
    )

    current_owner = replace(owner(), resource_kind="matchmaking")
    pipeline = PostgresExecutionGuard(Factory(Session()))
    with pytest.raises(ExecutionUnavailableError, match="execution_resource_mismatch"):
        pipeline.reconcile(current_owner)
