from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError

from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile
from huginn.management.domain.errors.errors import ConflictError
from huginn.management.domain.value_objects.account import NewAccount
from huginn.management.domain.value_objects.ideal_client_profile import (
    IdealClientProfileChanges,
    NewIdealClientProfile,
)
from huginn.management.domain.value_objects.service_offering import NewServiceOffering
from huginn.management.domain.value_objects.user import NewUser
from huginn.management.persistence.database.client import PsycopgDatabaseSession
from huginn.management.persistence.repositories.account import PostgresAccountRepository
from huginn.management.persistence.repositories.ideal_client_profile import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.persistence.repositories.service_offering import (
    PostgresServiceOfferingRepository,
)
from huginn.management.persistence.repositories.user import PostgresUserRepository
from huginn.management.presentation.api.mapping import (
    request_to_changes,
    request_to_domain,
)
from huginn.management.presentation.api.requests.ideal_client_profile import (
    IdealClientProfileCreateRequest as IcpCreate,
)
from huginn.management.presentation.api.requests.ideal_client_profile import (
    IdealClientProfileUpdateRequest as IcpPatch,
)
from huginn.management.presentation.api.responses.ideal_client_profile import (
    IdealClientProfileResponse,
)


def _profile(**overrides):
    values = {
        "id": uuid4(),
        "user_id": uuid4(),
        "name": "Target",
        "industries": ({"name": "SaaS"},),
        "company_sizes": ({"band": "11-100"},),
        "geographies": ({"kind": "country", "value": "DE"},),
        "exclusions": ({"kind": "industry", "name": "Gambling"},),
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
    }
    values.update(overrides)
    return IdealClientProfile(**values)


def test_icp_models_support_progressive_saves_and_replacement_patches():
    created = IcpCreate.model_validate({"name": "Target"})
    assert created.industries == created.company_sizes == created.geographies == []
    patch = IcpPatch.model_validate({"industries": [], "name": " Revised "})
    assert patch.supplied_fields == frozenset({"industries", "name"})
    assert patch.name == "Revised" and patch.industries == []
    with pytest.raises(ValidationError):
        IcpPatch.model_validate({"industries": None})
    with pytest.raises(ValidationError):
        IcpCreate.model_validate({"name": "Target", "user_id": str(uuid4())})
    company_id = uuid4()
    assert (
        IcpCreate.model_validate(
            {
                "name": "Target",
                "exclusions": [{"kind": "company", "company_id": str(company_id)}],
            }
        )
        .exclusions[0]
        .company_id
        == company_id
    )


def test_icp_response_serializes_company_exclusion_uuid():
    company_id = uuid4()
    profile = _profile(exclusions=({"kind": "company", "company_id": company_id},))
    response = IdealClientProfileResponse.model_validate(
        {
            **profile.__dict__,
            "industries": list(profile.industries),
            "company_sizes": list(profile.company_sizes),
            "geographies": list(profile.geographies),
            "exclusions": list(profile.exclusions),
        }
    )
    assert response.model_dump(mode="json")["exclusions"] == [
        {"kind": "company", "company_id": str(company_id)}
    ]


def test_icp_repository_crud_ownership_validation_and_referenced_delete(
    management_database_url,
):
    username = f"icp-{uuid4()}"
    with psycopg.connect(management_database_url) as connection:
        accounts = PostgresAccountRepository(PsycopgDatabaseSession(connection))
        users = PostgresUserRepository(PsycopgDatabaseSession(connection))
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
        repo = PostgresIdealClientProfileRepository(PsycopgDatabaseSession(connection))
        profile = repo.create(
            NewIdealClientProfile(
                owner.id,
                "Target",
                ({"name": "SaaS"},),
                ({"band": "11-100"},),
                ({"kind": "country", "value": "DE"},),
                (),
            )
        )
        changed = repo.update_owned(
            owner.id,
            profile.id,
            IdealClientProfileChanges(
                {"industries": (), "exclusions": ()},
                frozenset({"industries", "exclusions"}),
            ),
        )
        assert changed.industries == () and changed.exclusions == ()
        assert repo.get_owned(other.id, profile.id) is None
        assert repo.list_owned(owner.id, limit=1, offset=0).items[0].id == profile.id
        connection.execute(
            "UPDATE operational.ideal_client_profiles "
            "SET industries='[{\"unexpected\":true}]'::jsonb WHERE id=%s",
            (profile.id,),
        )
        with pytest.raises(ValidationError):
            repo.get_owned(owner.id, profile.id)
        connection.execute(
            "UPDATE operational.ideal_client_profiles SET industries='[]'::jsonb "
            "WHERE id=%s",
            (profile.id,),
        )
        offering = PostgresServiceOfferingRepository(
            PsycopgDatabaseSession(connection)
        ).create(NewServiceOffering(owner.id, "Consulting", "Audit"))
        connection.execute(
            "INSERT INTO operational.client_discovery_strategies "
            "(user_id,name,service_offering_id,ideal_client_profile_id) "
            "VALUES (%s,'Strategy',%s,%s)",
            (owner.id, offering.id, profile.id),
        )
        with pytest.raises(ConflictError):
            repo.delete_owned(owner.id, profile.id)
        connection.rollback()


def test_icp_company_exclusion_uuid_round_trips_jsonb_crud(management_database_url):
    username = f"icp-company-{uuid4()}"
    company_id = uuid4()
    with psycopg.connect(management_database_url) as connection:
        accounts = PostgresAccountRepository(PsycopgDatabaseSession(connection))
        users = PostgresUserRepository(PsycopgDatabaseSession(connection))
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
        repo = PostgresIdealClientProfileRepository(PsycopgDatabaseSession(connection))
        create = IcpCreate.model_validate(
            {
                "name": "Target",
                "exclusions": [{"kind": "company", "company_id": str(company_id)}],
            }
        )
        profile = repo.create(
            request_to_domain(create, NewIdealClientProfile, user_id=owner.id)
        )
        expected = {"kind": "company", "company_id": str(company_id)}
        assert profile.exclusions == (expected,)
        assert repo.get_owned(owner.id, profile.id).exclusions == (expected,)
        assert repo.list_owned(owner.id, limit=1, offset=0).items[0].exclusions == (
            expected,
        )
        updated = repo.update_owned(
            owner.id,
            profile.id,
            request_to_changes(
                IcpPatch.model_validate(
                    {"exclusions": [{"kind": "company", "company_id": str(company_id)}]}
                ),
                IdealClientProfileChanges,
            ),
        )
        assert updated.exclusions == (expected,)
