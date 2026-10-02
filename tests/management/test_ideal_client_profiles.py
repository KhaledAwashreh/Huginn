from datetime import UTC, datetime
from uuid import uuid4

import psycopg
import pytest
from pydantic import ValidationError

from huginn.management.domain import (
    ConflictError,
    IdealClientProfile,
    IdealClientProfileChanges,
    NewAccount,
    NewIdealClientProfile,
    NewServiceOffering,
    NewUser,
    NotFoundError,
)
from huginn.management.ideal_client_profiles import (
    IdealClientProfileService,
    PostgresIdealClientProfileRepository,
    evaluate_icp,
)
from huginn.management.identity import PostgresAccountRepository, PostgresUserRepository
from huginn.management.schemas import IcpCreate, IcpPatch
from huginn.management.service_offerings import PostgresServiceOfferingRepository
from tests.management.test_app_authentication import make_app
from tests.management.test_service_offering_app import Sessions


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
    with pytest.raises(ValidationError):
        IcpCreate.model_validate(
            {
                "name": "Target",
                "exclusions": [{"kind": "company", "company_id": str(uuid4())}],
            }
        )


def test_icp_service_serializes_json_native_company_exclusion_uuid():
    company_id = uuid4()
    profile = _profile(exclusions=({"kind": "company", "company_id": str(company_id)},))

    assert IdealClientProfileService._read(profile)["exclusions"] == [
        {"kind": "company", "company_id": str(company_id)}
    ]


def test_incomplete_icp_short_circuits_and_complete_filter_stays_flat():
    class Candidates:
        calls = []

        def find_candidates(self, criteria):
            self.calls.append(criteria)
            return ["candidate"]

    candidates = Candidates()
    for field in ("industries", "company_sizes", "geographies"):
        assert evaluate_icp(_profile(**{field: ()}), candidates) == []
    assert candidates.calls == []
    assert evaluate_icp(_profile(), candidates) == ["candidate"]
    criteria = candidates.calls[0]
    assert criteria.industries == ({"name": "SaaS"},)
    assert criteria.company_sizes == ({"band": "11-100"},)
    assert criteria.geographies == ({"kind": "country", "value": "DE"},)
    assert criteria.exclusions == ({"kind": "industry", "name": "Gambling"},)


def test_icp_repository_crud_ownership_validation_and_referenced_delete(
    management_database_url,
):
    username = f"icp-{uuid4()}"
    with psycopg.connect(management_database_url) as connection:
        accounts = PostgresAccountRepository(connection)
        users = PostgresUserRepository(connection)
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
        repo = PostgresIdealClientProfileRepository(connection)
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
        offering = PostgresServiceOfferingRepository(connection).create(
            NewServiceOffering(owner.id, "Consulting", "Audit")
        )
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
        accounts = PostgresAccountRepository(connection)
        users = PostgresUserRepository(connection)
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
        repo = PostgresIdealClientProfileRepository(connection)
        company_exclusion = {"kind": "company", "company_id": str(company_id)}
        profile = repo.create(
            NewIdealClientProfile(
                owner.id,
                "Target",
                (),
                (),
                (),
                (company_exclusion,),
            )
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
            IdealClientProfileChanges(
                {"exclusions": (company_exclusion,)}, frozenset({"exclusions"})
            ),
        )
        assert updated.exclusions == (expected,)


def test_icp_routes_are_authenticated_owner_scoped_and_map_statuses():
    class Icps:
        calls = []

        def create(self, principal, body):
            self.calls.append(("create", principal.user_id, body))
            return {
                "id": str(uuid4()),
                "user_id": str(principal.user_id),
                **body.model_dump(mode="json"),
            }

        def list(self, principal, *, limit, offset):
            self.calls.append(("list", principal.user_id, limit, offset))
            return {"items": [], "offset": offset, "limit": limit, "has_more": False}

        def get(self, principal, profile_id):
            raise NotFoundError("not found")

        def update(self, principal, profile_id, patch):
            return {
                "id": str(profile_id),
                "user_id": str(principal.user_id),
                "name": "Target",
                "industries": [],
                "company_sizes": [],
                "geographies": [],
                "exclusions": [],
            }

        def delete(self, principal, profile_id):
            raise ConflictError("referenced")

    sessions, icps = Sessions(), Icps()
    app, _, _ = make_app(sessions, ideal_client_profile_service=icps)
    client = app.test_client()
    token, (_session, principal, csrf) = next(iter(sessions.values.items()))
    client.set_cookie("huginn_management_session", token)
    created = client.post(
        "/api/v1/ideal-client-profiles",
        json={"name": "Target"},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201 and created.json["user_id"] == str(
        principal.user_id
    )
    assert (
        client.get("/api/v1/ideal-client-profiles?limit=7&offset=2").status_code == 200
    )
    profile_id = uuid4()
    assert client.get(f"/api/v1/ideal-client-profiles/{profile_id}").status_code == 404
    assert (
        client.patch(
            f"/api/v1/ideal-client-profiles/{profile_id}",
            json={"industries": []},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 200
    )
    assert (
        client.delete(
            f"/api/v1/ideal-client-profiles/{profile_id}",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/ideal-client-profiles",
            json={"name": "Target", "user_id": str(uuid4())},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 422
    )


def test_two_user_icp_routes_hide_cross_owner_resources():
    class OwnerScopedIcps:
        def __init__(self):
            self.records = {}

        def create(self, principal, body):
            profile_id = uuid4()
            record = {
                "id": str(profile_id),
                "user_id": str(principal.user_id),
                **body.model_dump(mode="json"),
            }
            self.records[profile_id] = record
            return record

        def get(self, principal, profile_id):
            record = self.records.get(profile_id)
            if record is None or record["user_id"] != str(principal.user_id):
                raise NotFoundError("not found")
            return record

        def update(self, principal, profile_id, patch):
            record = self.get(principal, profile_id)
            record.update(patch.model_dump(mode="json", exclude_unset=True))
            return record

        def delete(self, principal, profile_id):
            self.get(principal, profile_id)
            del self.records[profile_id]

    sessions, icps = Sessions(), OwnerScopedIcps()
    app, _, _ = make_app(sessions, ideal_client_profile_service=icps)
    client = app.test_client()
    first, second = list(sessions.values.items())
    first_token, (_, _, first_csrf) = first
    second_token, (_, _, second_csrf) = second
    client.set_cookie("huginn_management_session", first_token)
    created = client.post(
        "/api/v1/ideal-client-profiles",
        json={"name": "Progressive"},
        headers={"X-CSRF-Token": first_csrf},
    )
    assert created.status_code == 201 and created.json["industries"] == []
    path = f"/api/v1/ideal-client-profiles/{created.json['id']}"
    client.set_cookie("huginn_management_session", second_token)
    assert client.get(path).status_code == 404
    assert (
        client.patch(
            path,
            json={"geographies": []},
            headers={"X-CSRF-Token": second_csrf},
        ).status_code
        == 404
    )
    assert client.delete(path, headers={"X-CSRF-Token": second_csrf}).status_code == 404
    client.set_cookie("huginn_management_session", first_token)
    assert client.get(path).status_code == 200
