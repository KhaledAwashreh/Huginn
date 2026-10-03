from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)
from huginn.management.domain.common import Principal
from huginn.management.domain.professional_profile import ProfessionalProfile
from huginn.management.domain.session import Session
from huginn.management.domain.user import User
from huginn.management.routers.current_user import router
from huginn.management.security.tokens import digest_token

CSRF = "test-csrf-value"


class SelfService:
    def __init__(self, user_id):
        self.user_id = user_id
        self.calls = []
        self.user = User(
            id=user_id,
            account_id=uuid4(),
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.test",
            phone_number="+12025550123",
            country_of_residence="United Kingdom",
            timezone=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        now = datetime.now(UTC)
        self.profile = ProfessionalProfile(
            id=uuid4(),
            user_id=user_id,
            headline=None,
            professional_summary=None,
            skills=(),
            experience=(),
            previous_projects=(),
            created_at=now,
            updated_at=now,
        )

    def get_user(self, principal):
        self.calls.append(("get_user", principal.user_id))
        return self.user

    def update_user(self, principal, changes):
        self.calls.append(("update_user", principal.user_id, changes))
        return self.user

    def get_profile(self, principal):
        self.calls.append(("get_profile", principal.user_id))
        return self.profile

    def update_profile(self, principal, changes):
        self.calls.append(("update_profile", principal.user_id, changes))
        return self.profile


def client_for(service, user_id):
    app = create_app(
        ManagementConfig("unused", environment="test"),
        user_profile_service=service,
    )
    app.include_router(router)
    principal = Principal(uuid4(), user_id)
    now = datetime.now(UTC)
    session = Session(
        uuid4(),
        principal.account_id,
        "session-digest",
        digest_token(CSRF),
        now,
        now,
        None,
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque-session"
    )
    return TestClient(app)


def test_current_user_and_profile_reads_filter_private_and_undeclared_fields():
    user_id = uuid4()
    service = SelfService(user_id)
    service.profile = ProfessionalProfile(
        id=service.profile.id,
        user_id=user_id,
        headline=None,
        professional_summary=None,
        skills=({"name": "Python", "private": "drop-me"},),
        experience=(),
        previous_projects=(),
        created_at=service.profile.created_at,
        updated_at=service.profile.updated_at,
    )
    with client_for(service, user_id) as client:
        user = client.get("/api/v1/me")
        profile = client.get("/api/v1/me/professional-profile")

    assert user.status_code == profile.status_code == 200
    assert "account_id" not in user.json()
    assert profile.json()["skills"] == [{"name": "Python"}]
    assert "private" not in profile.text
    assert [call[1] for call in service.calls] == [user_id, user_id]


def test_patch_maps_only_supplied_values_and_replaces_or_clears_collections():
    user_id = uuid4()
    service = SelfService(user_id)
    with client_for(service, user_id) as client:
        user = client.patch(
            "/api/v1/me", json={"first_name": "Grace"}, headers={"X-CSRF-Token": CSRF}
        )
        profile = client.patch(
            "/api/v1/me/professional-profile",
            json={"skills": [{"name": "Python"}, {"name": "Python"}], "headline": None},
            headers={"X-CSRF-Token": CSRF},
        )
        cleared = client.patch(
            "/api/v1/me/professional-profile",
            json={"skills": [], "experience": [], "previous_projects": []},
            headers={"X-CSRF-Token": CSRF},
        )

    assert user.status_code == profile.status_code == cleared.status_code == 200
    assert service.calls[0][2].values == {"first_name": "Grace"}
    replacement = service.calls[1][2]
    assert replacement.values["skills"] == ({"name": "Python"}, {"name": "Python"})
    assert replacement.supplied_fields == frozenset({"skills", "headline"})
    assert service.calls[2][2].values == {
        "skills": (),
        "experience": (),
        "previous_projects": (),
    }


def test_invalid_or_forbidden_patch_returns_422_without_service_call():
    user_id = uuid4()
    service = SelfService(user_id)
    with client_for(service, user_id) as client:
        invalid = client.patch(
            "/api/v1/me", json={"email": None}, headers={"X-CSRF-Token": CSRF}
        )
        nested = client.patch(
            "/api/v1/me/professional-profile",
            json={
                "experience": [
                    {
                        "organization": "Acme",
                        "role": "Engineer",
                        "end_month": "2019-01",
                        "is_current": True,
                    }
                ]
            },
            headers={"X-CSRF-Token": CSRF},
        )
        ownership = client.patch(
            "/api/v1/me",
            json={"first_name": "Other", "user_id": str(uuid4())},
            headers={"X-CSRF-Token": CSRF},
        )

    assert [invalid.status_code, nested.status_code, ownership.status_code] == [422] * 3
    assert service.calls == []


def test_two_authenticated_principals_are_passed_as_the_only_ownership_context():
    first_id, second_id = uuid4(), uuid4()
    first_service, second_service = SelfService(first_id), SelfService(second_id)
    with (
        client_for(first_service, first_id) as first,
        client_for(second_service, second_id) as second,
    ):
        first.patch(
            "/api/v1/me", json={"first_name": "First"}, headers={"X-CSRF-Token": CSRF}
        )
        second.patch(
            "/api/v1/me", json={"first_name": "Second"}, headers={"X-CSRF-Token": CSRF}
        )

    assert first_service.calls[0][1] == first_id
    assert second_service.calls[0][1] == second_id
    assert first_id != second_id
