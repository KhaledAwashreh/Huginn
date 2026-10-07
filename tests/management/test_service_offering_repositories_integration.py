from uuid import uuid4

import psycopg
import pytest

from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.account import NewAccount
from huginn.management.domain.value_objects.service_offering import (
    NewServiceOffering,
    ServiceOfferingChanges,
)
from huginn.management.domain.value_objects.user import NewUser
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.service_offering import (
    PostgresServiceOfferingRepository,
)
from huginn.management.persistence.repositories.user import PostgresUserRepository


def test_offering_repository_crud_pagination_timestamp_and_ownership(
    management_database_url,
):
    username = f"offering-{uuid4()}"
    with psycopg.connect(management_database_url) as connection:
        connection.execute("SAVEPOINT offering_repository")
        accounts, users = (
            PostgresAccountRepository(PsycopgDatabaseSession(connection)),
            PostgresUserRepository(PsycopgDatabaseSession(connection)),
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
        other_account = accounts.create(NewAccount(username + "-other", "placeholder"))
        other = users.create(
            NewUser(
                other_account.id,
                "Grace",
                "Hopper",
                f"{username}-other@example.test",
                "+12025550124",
                "US",
            )
        )
        repo = PostgresServiceOfferingRepository(PsycopgDatabaseSession(connection))
        a = repo.create(NewServiceOffering(owner.id, "A", "First"))
        b = repo.create(NewServiceOffering(owner.id, "B", "Second"))
        connection.execute(
            "UPDATE operational.service_offerings "
            "SET created_at='2020-01-01T00:00:00Z', "
            "updated_at=now() - interval '1 day' WHERE id IN (%s,%s)",
            (a.id, b.id),
        )
        a, b = repo.get_owned(owner.id, a.id), repo.get_owned(owner.id, b.id)
        page = repo.list_owned(owner.id, limit=1, offset=0)
        assert [item.id for item in page.items] == [
            min((a, b), key=lambda item: item.id).id
        ]
        assert page.has_more
        # Equal creation timestamps use UUID as a stable tie breaker.
        assert repo.list_owned(owner.id, limit=2, offset=0).items == tuple(
            sorted((a, b), key=lambda item: (item.created_at, item.id))
        )
        changed = repo.update_owned(
            owner.id,
            a.id,
            ServiceOfferingChanges(
                {"description": "Revised"}, frozenset({"description"})
            ),
        )
        assert changed.description == "Revised" and changed.updated_at > a.updated_at
        assert repo.get_owned(other.id, a.id) is None
        assert (
            repo.update_owned(
                other.id,
                a.id,
                ServiceOfferingChanges({"name": "Stolen"}, frozenset({"name"})),
            )
            is None
        )
        assert not repo.delete_owned(other.id, a.id)
        # Database predicate is the boundary for cross-owner isolation; referenced delete is mapped.
        connection.execute(
            "INSERT INTO operational.ideal_client_profiles (user_id,name) VALUES (%s,'ICP')",
            (owner.id,),
        )
        profile_id = connection.execute(
            "SELECT id FROM operational.ideal_client_profiles WHERE user_id=%s",
            (owner.id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO operational.client_discovery_strategies (user_id,name,service_offering_id,ideal_client_profile_id) VALUES (%s,'Strategy',%s,%s)",
            (owner.id, a.id, profile_id),
        )
        with pytest.raises(ConflictError):
            repo.delete_owned(owner.id, a.id)
        connection.execute("ROLLBACK TO SAVEPOINT offering_repository")
        connection.execute("RELEASE SAVEPOINT offering_repository")
