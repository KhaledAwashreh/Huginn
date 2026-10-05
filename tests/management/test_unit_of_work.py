import pytest

from huginn.management.persistence.database.client import (
    ManagementConnectionFactory,
    PsycopgDatabaseSession,
)
from huginn.management.persistence.database.unit_of_work import UnitOfWork


class FakeConnection:
    def __init__(self, commit_error=None, rollback_error=None, close_error=None):
        self.commit_error = commit_error
        self.rollback_error = rollback_error
        self.close_error = close_error
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollbacks += 1
        if self.rollback_error:
            raise self.rollback_error

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


def _factory_for(connection):
    return ManagementConnectionFactory(
        "postgresql://example", connector=lambda *_a, **_k: connection
    )


def test_unit_of_work_commits_success_and_closes_connection():
    connection = FakeConnection()
    with UnitOfWork(_factory_for(connection)) as unit:
        assert isinstance(unit.connection, PsycopgDatabaseSession)
        unit.commit()
    assert (connection.commits, connection.rollbacks, connection.closed) == (1, 0, True)


def test_unit_of_work_allows_explicit_commit_or_rollback():
    committed = FakeConnection()
    with UnitOfWork(_factory_for(committed)) as unit:
        unit.commit()
    assert (committed.commits, committed.rollbacks, committed.closed) == (1, 0, True)

    rolled_back = FakeConnection()
    with UnitOfWork(_factory_for(rolled_back)) as unit:
        unit.rollback()
    assert (rolled_back.commits, rolled_back.rollbacks, rolled_back.closed) == (
        0,
        1,
        True,
    )


def test_unit_of_work_without_explicit_commit_rolls_back():
    connection = FakeConnection()
    with UnitOfWork(_factory_for(connection)):
        pass
    assert (connection.commits, connection.rollbacks, connection.closed) == (
        0,
        1,
        True,
    )


def test_unit_of_work_rolls_back_body_failure_and_closes_connection():
    connection = FakeConnection()
    with (
        pytest.raises(ValueError, match="body failed"),
        UnitOfWork(_factory_for(connection)),
    ):
        raise ValueError("body failed")
    assert (connection.commits, connection.rollbacks, connection.closed) == (0, 1, True)


def test_unit_of_work_rolls_back_commit_failure_and_closes_connection():
    connection = FakeConnection(RuntimeError("commit failed"))
    with (
        pytest.raises(RuntimeError, match="commit failed"),
        UnitOfWork(_factory_for(connection)) as unit,
    ):
        unit.commit()
    assert (connection.commits, connection.rollbacks, connection.closed) == (1, 1, True)


def test_unit_of_work_preserves_commit_failure_when_rollback_also_fails():
    commit_error = RuntimeError("commit failed")
    connection = FakeConnection(
        commit_error,
        RuntimeError("rollback failed"),
        RuntimeError("close failed"),
    )

    with (
        pytest.raises(RuntimeError, match="commit failed") as raised,
        UnitOfWork(_factory_for(connection)) as unit,
    ):
        unit.commit()

    assert raised.value is commit_error
    assert (connection.commits, connection.rollbacks, connection.closed) == (1, 1, True)


def test_unit_of_work_preserves_body_failure_when_cleanup_fails():
    body_error = ValueError("body failed")
    connection = FakeConnection(
        rollback_error=RuntimeError("rollback failed"),
        close_error=RuntimeError("close failed"),
    )

    with (
        pytest.raises(ValueError, match="body failed") as raised,
        UnitOfWork(_factory_for(connection)),
    ):
        raise body_error

    assert raised.value is body_error
    assert (connection.commits, connection.rollbacks, connection.closed) == (0, 1, True)


def test_unit_of_work_preserves_rollback_failure_when_close_also_fails():
    rollback_error = RuntimeError("rollback failed")
    connection = FakeConnection(
        rollback_error=rollback_error,
        close_error=RuntimeError("close failed"),
    )

    with (
        pytest.raises(RuntimeError, match="rollback failed") as raised,
        UnitOfWork(_factory_for(connection)),
    ):
        pass

    assert raised.value is rollback_error
    assert (connection.commits, connection.rollbacks, connection.closed) == (0, 1, True)


def test_unit_of_work_propagates_close_failure_without_an_active_error():
    close_error = RuntimeError("close failed")
    connection = FakeConnection(close_error=close_error)

    with (
        pytest.raises(RuntimeError, match="close failed") as raised,
        UnitOfWork(_factory_for(connection)) as unit,
    ):
        unit.commit()

    assert raised.value is close_error
    assert (connection.commits, connection.rollbacks, connection.closed) == (1, 0, True)


def test_connection_factory_is_lazy_and_returns_connection():
    connection = FakeConnection()
    calls = []
    factory = ManagementConnectionFactory(
        "postgresql://example",
        connector=lambda *args, **kwargs: calls.append((args, kwargs)) or connection,
    )
    assert calls == []
    assert isinstance(factory.connect(), PsycopgDatabaseSession)
    assert len(calls) == 1
