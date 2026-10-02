import pytest

from huginn.management.database import ManagementConnectionFactory, UnitOfWork


class FakeConnection:
    def __init__(self, commit_error=None):
        self.commit_error = commit_error
        self.commits = 0
        self.rollbacks = 0
        self.closed = False

    def commit(self):
        self.commits += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _factory_for(connection):
    return ManagementConnectionFactory(
        "postgresql://example", connector=lambda *_a, **_k: connection
    )


def test_unit_of_work_commits_success_and_closes_connection():
    connection = FakeConnection()
    with UnitOfWork(_factory_for(connection)) as unit:
        assert unit.connection is connection
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


def test_connection_factory_is_lazy_and_returns_connection():
    connection = FakeConnection()
    calls = []
    factory = ManagementConnectionFactory(
        "postgresql://example",
        connector=lambda *args, **kwargs: calls.append((args, kwargs)) or connection,
    )
    assert calls == []
    assert factory.connect() is connection
    assert len(calls) == 1
