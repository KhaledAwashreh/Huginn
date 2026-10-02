from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError

from huginn.management.database import ManagementConnectionFactory, UnitOfWork
from huginn.management.discovery_strategies import (
    ClientDiscoveryStrategyService,
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.domain import (
    NewAccount,
    NewClientDiscoveryStrategy,
    NewIdealClientProfile,
    NewServiceOffering,
    NewUser,
    NotFoundError,
    Principal,
)
from huginn.management.ideal_client_profiles import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.identity import PostgresAccountRepository, PostgresUserRepository
from huginn.management.schemas import StrategyCreate, StrategyPatch
from huginn.management.service_offerings import PostgresServiceOfferingRepository
from tests.management.test_app_authentication import make_app
from tests.management.test_service_offering_app import Sessions


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
    from huginn.management.domain import Principal

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
        lambda: uow, strategies_factory=lambda _uow: Strategies()
    )

    with pytest.raises(NotFoundError, match="Strategy not found"):
        service.update(
            Principal(uuid4(), uuid4()), uuid4(), StrategyPatch(name="Changed")
        )

    assert uow.committed is False


def test_strategy_routes_are_owner_scoped_and_filter_active_state():
    class Strategies:
        calls = []

        def create(self, principal, body):
            self.calls.append(("create", principal.user_id))
            return {
                "id": str(uuid4()),
                "user_id": str(principal.user_id),
                **body.model_dump(mode="json"),
            }

        def list(self, principal, *, limit, offset, active):
            self.calls.append(("list", principal.user_id, limit, offset, active))
            return {"items": [], "offset": offset, "limit": limit, "has_more": False}

        def get(self, principal, strategy_id):
            raise NotFoundError("not found")

        def update(self, principal, strategy_id, patch):
            return {
                "id": str(strategy_id),
                "user_id": str(principal.user_id),
                "name": "Weekly",
                "service_offering_id": str(uuid4()),
                "ideal_client_profile_id": str(uuid4()),
                "is_active": patch.is_active,
            }

        def delete(self, principal, strategy_id):
            return None

    sessions, strategies = Sessions(), Strategies()
    app, _, _ = make_app(sessions, discovery_strategy_service=strategies)
    client = app.test_client()
    token, (_, principal, csrf) = next(iter(sessions.values.items()))
    client.set_cookie("huginn_management_session", token)
    payload = {
        "name": "Weekly",
        "service_offering_id": str(uuid4()),
        "ideal_client_profile_id": str(uuid4()),
    }
    created = client.post(
        "/api/v1/discovery-strategies",
        json=payload,
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201 and created.json["is_active"] is False
    listing = client.get("/api/v1/discovery-strategies?active=true&limit=4")
    assert listing.status_code == 200
    assert strategies.calls[-1] == ("list", principal.user_id, 4, 0, True)
    assert client.get("/api/v1/discovery-strategies?active=1").status_code == 422
    assert (
        client.post(
            "/api/v1/discovery-strategies",
            json={**payload, "user_id": str(uuid4())},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 422
    )


def test_two_user_strategy_member_routes_hide_cross_owner_records():
    class OwnerScopedStrategies:
        def __init__(self):
            self.records = {}

        def create(self, principal, body):
            strategy_id = uuid4()
            record = {
                "id": str(strategy_id),
                "user_id": str(principal.user_id),
                **body.model_dump(mode="json"),
            }
            self.records[strategy_id] = record
            return record

        def get(self, principal, strategy_id):
            record = self.records.get(strategy_id)
            if record is None or record["user_id"] != str(principal.user_id):
                raise NotFoundError("not found")
            return record

        def update(self, principal, strategy_id, patch):
            record = self.get(principal, strategy_id)
            record.update(patch.model_dump(mode="json", exclude_unset=True))
            return record

        def delete(self, principal, strategy_id):
            self.get(principal, strategy_id)
            del self.records[strategy_id]

    sessions, strategies = Sessions(), OwnerScopedStrategies()
    app, _, _ = make_app(sessions, discovery_strategy_service=strategies)
    client = app.test_client()
    first, second = list(sessions.values.items())
    first_token, (_, _, first_csrf) = first
    second_token, (_, _, second_csrf) = second
    client.set_cookie("huginn_management_session", first_token)
    created = client.post(
        "/api/v1/discovery-strategies",
        json={
            "name": "Weekly",
            "service_offering_id": str(uuid4()),
            "ideal_client_profile_id": str(uuid4()),
            "is_active": True,
        },
        headers={"X-CSRF-Token": first_csrf},
    )
    assert created.status_code == 201
    path = f"/api/v1/discovery-strategies/{created.json['id']}"
    client.set_cookie("huginn_management_session", second_token)
    assert client.get(path).status_code == 404
    assert (
        client.patch(
            path,
            json={"is_active": False},
            headers={"X-CSRF-Token": second_csrf},
        ).status_code
        == 404
    )
    assert client.delete(path, headers={"X-CSRF-Token": second_csrf}).status_code == 404
    client.set_cookie("huginn_management_session", first_token)
    assert (
        client.patch(
            path,
            json={"is_active": False},
            headers={"X-CSRF-Token": first_csrf},
        ).json["is_active"]
        is False
    )


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
    sessions = Sessions()
    token, (session, principal, csrf) = next(iter(sessions.values.items()))
    sessions.values[token] = (session, Principal(principal.account_id, owner.id), csrf)
    app, _, _ = make_app(sessions, discovery_strategy_service=service)

    try:
        client = app.test_client()
        client.set_cookie("huginn_management_session", token)
        response = client.patch(
            f"/api/v1/discovery-strategies/{strategy.id}",
            json={"service_offering_id": str(offering.id)},
            headers={"X-CSRF-Token": csrf},
        )

        assert state == {
            "preflighted": True,
            "offering_checked": True,
            "profile_checked": True,
            "deleted": True,
        }
        assert response.status_code == 404
        assert response.json["error"]["code"] == "not_found"
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
