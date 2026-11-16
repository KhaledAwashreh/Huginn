from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.business import Business
from huginn.management.domain.entities.session import Session
from huginn.management.domain.value_objects.common import Principal
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)
from huginn.management.security.tokens import digest_token

CSRF = "business-csrf-value"


def test_business_profile_is_principal_scoped_private_and_csrf_protected():
    now = datetime.now(UTC)
    principal = Principal(uuid4(), uuid4())
    business = Business(
        uuid4(), principal.user_id, None, None, None, None, None, None, now, now
    )
    observed = []

    class Profiles:
        def get(self, requested_principal):
            observed.append(("get", requested_principal.user_id))
            return business

        def update(self, requested_principal, changes):
            observed.append(("update", requested_principal.user_id, changes.values))
            return Business(
                business.id,
                business.owner_user_id,
                changes.values.get("name", business.name),
                business.tagline,
                business.website,
                business.location,
                business.description,
                business.capabilities,
                business.created_at,
                now,
            )

    class Preferences:
        def get(self, _principal):
            raise AssertionError

        def update(self, _principal, _changes):
            raise AssertionError

    app = create_app(
        ManagementConfig("unused", environment="test"),
        business_profile_service=Profiles(),
        business_recommendation_preferences_service=Preferences(),
    )
    session = Session(
        uuid4(),
        principal.account_id,
        "token-digest",
        digest_token(CSRF),
        now,
        now,
        None,
    )
    authenticated = AuthenticatedSession(principal, session, "opaque-token")
    app.dependency_overrides[get_authenticated_session] = lambda: authenticated

    with TestClient(app) as client:
        client.cookies.set("huginn_management_session", "opaque-token")
        response = client.get("/api/v1/me/business")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["vary"] == "Cookie"
        assert response.json()["id"] == str(business.id)
        assert response.json()["owner_user_id"] == str(principal.user_id)
        assert response.json()["name"] is None

        rejected = client.patch("/api/v1/me/business", json={"name": "Studio"})
        assert rejected.status_code == 403
        updated = client.patch(
            "/api/v1/me/business",
            json={"name": "Studio"},
            headers={"X-CSRF-Token": CSRF},
        )
        assert updated.status_code == 200
        assert updated.json()["name"] == "Studio"
        assert updated.headers["cache-control"] == "no-store"

        foreign_owner = client.patch(
            "/api/v1/me/business",
            json={"business_id": str(uuid4()), "name": "Other"},
            headers={"X-CSRF-Token": CSRF},
        )
        assert foreign_owner.status_code == 422

    assert observed == [
        ("get", principal.user_id),
        ("update", principal.user_id, {"name": "Studio"}),
    ]
