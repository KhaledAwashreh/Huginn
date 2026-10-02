from uuid import uuid4

from huginn.management.discovery_strategies import (
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.domain import (
    ClientDiscoveryStrategyChanges,
    IdealClientProfileChanges,
    ProfessionalProfileChanges,
    ServiceOfferingChanges,
    UserChanges,
)
from huginn.management.ideal_client_profiles import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.identity import (
    PostgresAccountRepository,
    PostgresProfessionalProfileRepository,
    PostgresUserRepository,
)
from huginn.management.service_offerings import PostgresServiceOfferingRepository


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
        return None


class Connection:
    def __init__(self):
        self.calls = []

    def cursor(self):
        return Cursor(self)


def test_all_management_updated_at_updates_use_write_time_clock():
    connection = Connection()
    account_id, user_id, offering_id, profile_id, strategy_id = (
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
        uuid4(),
    )

    accounts = PostgresAccountRepository(connection)
    accounts.set_status(account_id, "disabled")
    accounts.set_password_hash(account_id, "new-hash")
    PostgresUserRepository(connection).update(
        user_id, UserChanges({"first_name": "Grace"}, frozenset({"first_name"}))
    )
    PostgresProfessionalProfileRepository(connection).update_owned(
        user_id,
        ProfessionalProfileChanges({"headline": "Engineer"}, frozenset({"headline"})),
    )
    PostgresServiceOfferingRepository(connection).update_owned(
        user_id,
        offering_id,
        ServiceOfferingChanges({"description": "Revised"}, frozenset({"description"})),
    )
    PostgresIdealClientProfileRepository(connection).update_owned(
        user_id,
        profile_id,
        IdealClientProfileChanges({"name": "Revised"}, frozenset({"name"})),
    )
    PostgresClientDiscoveryStrategyRepository(connection).update_owned(
        user_id,
        strategy_id,
        ClientDiscoveryStrategyChanges({"is_active": True}, frozenset({"is_active"})),
    )

    assert len(connection.calls) == 7
    for query, _params in connection.calls:
        assert "clock_timestamp()" in query
        assert "updated_at = now()" not in query
        assert "updated_at=now()" not in query
