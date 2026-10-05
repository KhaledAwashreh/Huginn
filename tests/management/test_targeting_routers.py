from dataclasses import replace
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.client_discovery_strategy import (
    ClientDiscoveryStrategy,
)
from huginn.management.domain.entities.ideal_client_profile import IdealClientProfile
from huginn.management.domain.entities.session import Session
from huginn.management.domain.errors.errors import (
    ConflictError,
    NotFoundError,
)
from huginn.management.domain.value_objects.common import (
    Page,
    Principal,
)
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
    require_csrf,
)
from huginn.management.presentation.api.routers.discovery_strategies import (
    router as strategies_router,
)
from huginn.management.presentation.api.routers.ideal_client_profiles import (
    router as profiles_router,
)

NOW = datetime(2026, 10, 3, tzinfo=UTC)
CSRF = "test-csrf"


class ProfileService:
    def __init__(self):
        self.values = {}
        self.calls = []

    def create(self, principal, value):
        self.calls.append(("create", principal.user_id, value))
        profile = IdealClientProfile(
            uuid4(),
            principal.user_id,
            value.name,
            value.industries,
            value.company_sizes,
            value.geographies,
            value.exclusions,
            NOW,
            NOW,
        )
        self.values[profile.id] = profile
        return profile

    def list(self, principal, *, limit, offset):
        self.calls.append(("list", principal.user_id, limit, offset))
        if offset > 9_223_372_036_854_775_807:
            return Page((), offset, limit, False)
        owned = [
            value
            for value in self.values.values()
            if value.user_id == principal.user_id
        ]
        return Page(tuple(owned[offset : offset + limit]), offset, limit, False)

    def get(self, principal, profile_id):
        value = self.values.get(profile_id)
        if value is None or value.user_id != principal.user_id:
            raise NotFoundError("not found")
        return value

    def update(self, principal, profile_id, changes):
        current = self.get(principal, profile_id)
        self.calls.append(("update", changes))
        updated = replace(current, **changes.values, updated_at=NOW)
        self.values[profile_id] = updated
        return updated

    def delete(self, principal, profile_id):
        if (
            profile_id not in self.values
            or self.values[profile_id].user_id != principal.user_id
        ):
            raise NotFoundError("not found")
        raise ConflictError("referenced")


class StrategyService:
    def __init__(self):
        self.values = {}
        self.calls = []

    def create(self, principal, value):
        self.calls.append(("create", principal.user_id, value))
        strategy = ClientDiscoveryStrategy(
            uuid4(),
            principal.user_id,
            value.name,
            value.service_offering_id,
            value.ideal_client_profile_id,
            value.is_active,
            NOW,
            NOW,
        )
        self.values[strategy.id] = strategy
        return strategy

    def list(self, principal, *, limit, offset, active):
        self.calls.append(("list", principal.user_id, limit, offset, active))
        if offset > 9_223_372_036_854_775_807:
            return Page((), offset, limit, False)
        owned = [
            value
            for value in self.values.values()
            if value.user_id == principal.user_id
            and (active is None or value.is_active is active)
        ]
        return Page(tuple(owned[offset : offset + limit]), offset, limit, False)

    def get(self, principal, strategy_id):
        value = self.values.get(strategy_id)
        if value is None or value.user_id != principal.user_id:
            raise NotFoundError("not found")
        return value

    def update(self, principal, strategy_id, changes):
        current = self.get(principal, strategy_id)
        self.calls.append(("update", changes))
        updated = replace(current, **changes.values, updated_at=NOW)
        self.values[strategy_id] = updated
        return updated

    def delete(self, principal, strategy_id):
        self.get(principal, strategy_id)
        del self.values[strategy_id]


def _client(profile_service=None, strategy_service=None):
    principal = Principal(uuid4(), uuid4())
    session = Session(
        uuid4(), principal.account_id, "token-digest", "csrf-digest", NOW, NOW, None
    )
    authenticated = AuthenticatedSession(principal, session, "opaque-token")
    app = create_app(
        ManagementConfig("unused", environment="test"),
        ideal_client_profile_service=profile_service or ProfileService(),
        discovery_strategy_service=strategy_service or StrategyService(),
    )
    app.include_router(profiles_router)
    app.include_router(strategies_router)
    app.dependency_overrides[get_authenticated_session] = lambda: authenticated
    app.dependency_overrides[require_csrf] = lambda: authenticated
    return TestClient(app), principal


def test_icp_routes_map_typed_collections_pages_uuid_and_errors():
    service = ProfileService()
    client, principal = _client(profile_service=service)
    with client:
        created = client.post("/api/v1/ideal-client-profiles", json={"name": "Target"})
        assert created.status_code == 201
        assert created.json()["user_id"] == str(principal.user_id)
        assert created.json()["industries"] == []
        profile_id = created.json()["id"]
        assert isinstance(service.calls[-1][2].industries, tuple)

        replaced = client.patch(
            f"/api/v1/ideal-client-profiles/{profile_id}",
            json={"industries": [{"name": "SaaS"}], "geographies": []},
        )
        assert replaced.status_code == 200
        assert replaced.json()["industries"] == [{"name": "SaaS"}]
        assert replaced.json()["geographies"] == []
        assert service.calls[-1][1].supplied_fields == frozenset(
            {"industries", "geographies"}
        )

        listing = client.get("/api/v1/ideal-client-profiles?limit=7&offset=0")
        assert (
            listing.status_code == 200
            and listing.json()["items"][0]["id"] == profile_id
        )
        assert service.calls[-1] == ("list", principal.user_id, 7, 0)
        overflow = client.get(
            "/api/v1/ideal-client-profiles?offset=9223372036854775808"
        )
        assert overflow.status_code == 422
        assert service.calls[-1] == ("list", principal.user_id, 7, 0)
        assert client.get("/api/v1/ideal-client-profiles/not-a-uuid").status_code == 422
        assert client.get(f"/api/v1/ideal-client-profiles/{uuid4()}").status_code == 404
        assert (
            client.delete(f"/api/v1/ideal-client-profiles/{profile_id}").status_code
            == 409
        )
        assert client.get("/api/v1/ideal-client-profiles?limit=101").status_code == 422


def test_strategy_routes_default_inactive_filter_activate_and_hide_other_owner():
    service = StrategyService()
    client, principal = _client(strategy_service=service)
    payload = {
        "name": "Weekly",
        "service_offering_id": str(uuid4()),
        "ideal_client_profile_id": str(uuid4()),
    }
    with client:
        created = client.post("/api/v1/discovery-strategies", json=payload)
        assert created.status_code == 201
        strategy_id = created.json()["id"]
        assert created.json()["is_active"] is False
        assert service.calls[-1][2].is_active is False

        activated = client.patch(
            f"/api/v1/discovery-strategies/{strategy_id}", json={"is_active": True}
        )
        assert activated.status_code == 200 and activated.json()["is_active"] is True
        listing = client.get(
            "/api/v1/discovery-strategies?active=true&limit=4&offset=1"
        )
        assert listing.status_code == 200
        assert service.calls[-1] == ("list", principal.user_id, 4, 1, True)
        overflow = client.get("/api/v1/discovery-strategies?offset=9223372036854775808")
        assert overflow.status_code == 422
        assert service.calls[-1] == ("list", principal.user_id, 4, 1, True)
        assert (
            client.get("/api/v1/discovery-strategies?active=perhaps").status_code == 422
        )
        assert client.get(f"/api/v1/discovery-strategies/{uuid4()}").status_code == 404
        assert (
            client.delete(f"/api/v1/discovery-strategies/{strategy_id}").status_code
            == 204
        )
