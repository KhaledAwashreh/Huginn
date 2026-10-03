from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError

from huginn.management.database import ManagementConnectionFactory, UnitOfWork
from huginn.management.domain.account import NewAccount
from huginn.management.domain.client_discovery_strategy import (
    ClientDiscoveryStrategyChanges,
    NewClientDiscoveryStrategy,
)
from huginn.management.domain.common import Principal
from huginn.management.domain.ideal_client_profile import NewIdealClientProfile
from huginn.management.domain.service_offering import NewServiceOffering
from huginn.management.domain.user import NewUser
from huginn.management.errors.domain import NotFoundError
from huginn.management.repositories.postgres.account import PostgresAccountRepository
from huginn.management.repositories.postgres.discovery_strategy import (
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.repositories.postgres.ideal_client_profile import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.repositories.postgres.service_offering import (
    PostgresServiceOfferingRepository,
)
from huginn.management.repositories.postgres.user import PostgresUserRepository
from huginn.management.requests.discovery_strategy import (
    DiscoveryStrategyCreateRequest as StrategyCreate,
)
from huginn.management.requests.discovery_strategy import (
    DiscoveryStrategyUpdateRequest as StrategyPatch,
)
from huginn.management.services.discovery_strategies import (
    ClientDiscoveryStrategyService,
)


def test_strategy_models_are_strict_and_default_inactive():
    payload = {
        "name": "Weekly",
        "service_offering_id": uuid4(),
        "ideal_client_profile_id": uuid4(),
    }
    assert StrategyCreate.model_validate(payload).is_active is False
    assert StrategyPatch.model_validate(
        {"is_active": True}
    ).supplied_fields == frozenset({"is_active"})
    with pytest.raises(ValidationError):
        StrategyCreate.model_validate({**payload, "user_id": uuid4()})
    with pytest.raises(ValidationError):
        StrategyPatch.model_validate({"is_active": None})


def test_strategy_repository_supports_shared_active_references_and_filtering(
    management_database_url,
):
    username = f"strategy-{uuid4()}"
    with psycopg.connect(management_database_url) as connection:
        accounts, users = (
            PostgresAccountRepository(connection),
            PostgresUserRepository(connection),
        )
        owner = users.create(
            NewUser(
                accounts.create(NewAccount(username, "placeholder")).id,
                "Ada",
                "Lovelace",
                f"{username}@example.test",
                "+12025550123",
                "US",
            )
        )
        other = users.create(
            NewUser(
                accounts.create(NewAccount(username + "-other", "placeholder")).id,
                "Grace",
                "Hopper",
                f"{username}-other@example.test",
                "+12025550124",
                "US",
            )
        )
        offering = PostgresServiceOfferingRepository(connection).create(
            NewServiceOffering(owner.id, "Consulting", "Audit")
        )
        profile = PostgresIdealClientProfileRepository(connection).create(
            NewIdealClientProfile(owner.id, "Target", (), (), (), ())
        )
        repo = PostgresClientDiscoveryStrategyRepository(connection)
        first = repo.create(
            NewClientDiscoveryStrategy(owner.id, "One", offering.id, profile.id, True)
        )
        second = repo.create(
            NewClientDiscoveryStrategy(owner.id, "Two", offering.id, profile.id, True)
        )
        active = repo.list_owned(owner.id, limit=10, offset=0, active=True)
        assert {item.id for item in active.items} == {first.id, second.id}
        assert repo.get_owned(other.id, first.id) is None
        connection.execute("SAVEPOINT cross_owner_strategy")
        with pytest.raises(NotFoundError):
            repo.create(
                NewClientDiscoveryStrategy(
                    other.id, "Injected", offering.id, profile.id, False
                )
            )
        connection.execute("ROLLBACK TO SAVEPOINT cross_owner_strategy")
        connection.rollback()


def test_strategy_service_preflights_owned_references_before_write():
    class Uow:
        connection = object()
        committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            self.committed = True

    class Missing:
        def get_owned(self, _user_id, _resource_id):
            return None

    class Strategies:
        def create(self, _value):
            raise AssertionError("write must not run")

    service = ClientDiscoveryStrategyService(
        Uow,
        strategies_factory=lambda _uow: Strategies(),
        offerings_factory=lambda _uow: Missing(),
        profiles_factory=lambda _uow: Missing(),
    )
    with pytest.raises(NotFoundError):
        service.create(
            Principal(uuid4(), uuid4()),
            StrategyCreate(
                name="Nope",
                service_offering_id=uuid4(),
                ideal_client_profile_id=uuid4(),
            ),
        )


def test_strategy_service_maps_update_lost_after_preflight_to_not_found():
    class Uow:
        connection = object()
        committed = False

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def commit(self):
            self.committed = True

    class Strategies:
        def get_owned(self, _user_id, _strategy_id):
            return SimpleNamespace(
                service_offering_id=uuid4(), ideal_client_profile_id=uuid4()
            )

        def update_owned(self, _user_id, _strategy_id, _changes):
            return None

    uow = Uow()
    service = ClientDiscoveryStrategyService(
        lambda: uow,
        strategies_factory=lambda _uow: Strategies(),
        offerings_factory=lambda _uow: None,
        profiles_factory=lambda _uow: None,
    )

    with pytest.raises(NotFoundError, match="Strategy not found"):
        service.update(
            Principal(uuid4(), uuid4()),
            uuid4(),
            ClientDiscoveryStrategyChanges({"name": "Changed"}, frozenset({"name"})),
        )

    assert uow.committed is False


def test_live_strategy_update_losing_to_concurrent_delete_returns_not_found(
    management_database_url,
):
    username = f"strategy-delete-race-{uuid4()}"
    with psycopg.connect(management_database_url) as connection:
        accounts, users = (
            PostgresAccountRepository(connection),
            PostgresUserRepository(connection),
        )
        account = accounts.create(NewAccount(username, "placeholder"))
        owner = users.create(
            NewUser(
                account.id,
                "Ada",
                "Lovelace",
                f"{username}@example.test",
                "+12025550123",
                "US",
            )
        )
        offering = PostgresServiceOfferingRepository(connection).create(
            NewServiceOffering(owner.id, "Consulting", "Audit")
        )
        profile = PostgresIdealClientProfileRepository(connection).create(
            NewIdealClientProfile(owner.id, "Target", (), (), (), ())
        )
        strategy = PostgresClientDiscoveryStrategyRepository(connection).create(
            NewClientDiscoveryStrategy(
                owner.id, "Weekly", offering.id, profile.id, False
            )
        )

    factory = ManagementConnectionFactory(management_database_url)
    state = {
        "preflighted": False,
        "offering_checked": False,
        "profile_checked": False,
        "deleted": False,
    }

    class RacingStrategies:
        def __init__(self, connection):
            self.repository = PostgresClientDiscoveryStrategyRepository(connection)

        def get_owned(self, user_id, strategy_id):
            value = self.repository.get_owned(user_id, strategy_id)
            state["preflighted"] = value is not None
            return value

        def update_owned(self, user_id, strategy_id, changes):
            assert state["preflighted"]
            with psycopg.connect(management_database_url) as delete_connection:
                state["deleted"] = PostgresClientDiscoveryStrategyRepository(
                    delete_connection
                ).delete_owned(user_id, strategy_id)
                delete_connection.commit()
            return self.repository.update_owned(user_id, strategy_id, changes)

    class CheckedOfferings:
        def __init__(self, connection):
            self.repository = PostgresServiceOfferingRepository(connection)

        def get_owned(self, user_id, offering_id):
            value = self.repository.get_owned(user_id, offering_id)
            state["offering_checked"] = value is not None
            return value

    class CheckedProfiles:
        def __init__(self, connection):
            self.repository = PostgresIdealClientProfileRepository(connection)

        def get_owned(self, user_id, profile_id):
            value = self.repository.get_owned(user_id, profile_id)
            state["profile_checked"] = value is not None
            return value

    service = ClientDiscoveryStrategyService(
        lambda: UnitOfWork(factory),
        strategies_factory=lambda uow: RacingStrategies(uow.connection),
        offerings_factory=lambda uow: CheckedOfferings(uow.connection),
        profiles_factory=lambda uow: CheckedProfiles(uow.connection),
    )
    try:
        with pytest.raises(NotFoundError, match="Strategy not found"):
            service.update(
                Principal(account.id, owner.id),
                strategy.id,
                ClientDiscoveryStrategyChanges(
                    {"service_offering_id": offering.id},
                    frozenset({"service_offering_id"}),
                ),
            )
        assert state == {
            "preflighted": True,
            "offering_checked": True,
            "profile_checked": True,
            "deleted": True,
        }
    finally:
        with psycopg.connect(management_database_url) as cleanup_connection:
            cleanup_connection.execute(
                "DELETE FROM operational.client_discovery_strategies WHERE id = %s",
                (strategy.id,),
            )
            cleanup_connection.execute(
                "DELETE FROM operational.ideal_client_profiles WHERE id = %s",
                (profile.id,),
            )
            cleanup_connection.execute(
                "DELETE FROM operational.service_offerings WHERE id = %s",
                (offering.id,),
            )
            cleanup_connection.execute(
                "DELETE FROM operational.users WHERE id = %s", (owner.id,)
            )
            cleanup_connection.execute(
                "DELETE FROM operational.accounts WHERE id = %s", (account.id,)
            )
            cleanup_connection.commit()
