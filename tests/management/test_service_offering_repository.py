from uuid import uuid4

import pytest

from huginn.management.domain.service_offering import ServiceOfferingChanges
from huginn.management.repositories.postgres.service_offering import (
    PostgresServiceOfferingRepository,
)


class Cursor:
    def __init__(self, connection):
        self.connection = connection

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        self.connection.calls.append((query, params))

    def fetchone(self):
        return self.connection.row


class Connection:
    def __init__(self):
        self.calls = []
        self.row = None

    def cursor(self):
        return Cursor(self)

    def execute(self, query, params):
        self.calls.append((query, params))
        return type("Result", (), {"fetchall": lambda _self: []})()


def test_offering_repository_scopes_each_member_operation_and_whitelists_updates():
    connection = Connection()
    repo = PostgresServiceOfferingRepository(connection)
    user_id, offering_id = uuid4(), uuid4()
    repo.get_owned(user_id, offering_id)
    repo.update_owned(
        user_id,
        offering_id,
        ServiceOfferingChanges({"name": "Name"}, frozenset({"name"})),
    )
    repo.delete_owned(user_id, offering_id)
    for query, params in connection.calls:
        assert "user_id = %s" in query
        assert user_id in params
    update_sql = connection.calls[1][0]
    assert "name = %s" in update_sql and "updated_at = clock_timestamp()" in update_sql
    assert all(value in update_sql for value in ("WHERE user_id", "AND id = %s"))
    count = len(connection.calls)
    with pytest.raises(ValueError):
        repo.update_owned(
            user_id,
            offering_id,
            ServiceOfferingChanges({"user_id": str(uuid4())}, frozenset({"user_id"})),
        )
    assert len(connection.calls) == count


def test_offering_list_uses_created_id_order_and_fetches_one_extra():
    connection = Connection()
    repo = PostgresServiceOfferingRepository(connection)
    user_id = uuid4()
    repo.list_owned(user_id, limit=5, offset=8)
    query, params = connection.calls[0]
    assert "WHERE user_id = %s" in query
    assert "ORDER BY created_at, id" in query
    assert "LIMIT %s OFFSET %s" in query and params == (user_id, 6, 8)
