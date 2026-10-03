from uuid import uuid4

from huginn.management.domain.client_discovery_strategy import (
    ClientDiscoveryStrategyChanges,
)
from huginn.management.domain.ideal_client_profile import IdealClientProfileChanges
from huginn.management.domain.professional_profile import ProfessionalProfileChanges
from huginn.management.domain.service_offering import ServiceOfferingChanges
from huginn.management.domain.user import UserChanges
from huginn.management.repositories.postgres.account import PostgresAccountRepository
from huginn.management.repositories.postgres.discovery_strategy import (
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.repositories.postgres.ideal_client_profile import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.repositories.postgres.professional_profile import (
    PostgresProfessionalProfileRepository,
)
from huginn.management.repositories.postgres.service_offering import (
    PostgresServiceOfferingRepository,
)
from huginn.management.repositories.postgres.user import PostgresUserRepository


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
    PostgresProfessionalProfileRepository(connection).update(
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
