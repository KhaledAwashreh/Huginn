from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.common import (
    Page,
    Principal,
)
from huginn.management.domain.service_offering import (
    NewServiceOffering,
    ServiceOffering,
    ServiceOfferingChanges,
)
from huginn.management.domain.session import Session
from huginn.management.errors.domain import (
    ConflictError,
    NotFoundError,
)
from huginn.management.routers.service_offerings import router
from huginn.management.services.authentication import AuthenticatedSession

SESSION_COOKIE = "huginn_management_session"
SESSION_TOKEN = "test-session-token"
CSRF_TOKEN = "test-csrf-token"


def _digest(value: str) -> str:
    return sha256(value.encode()).hexdigest()


class FakeAuthentication:
    def __init__(self, owner_id: UUID):
        self.principal = Principal(uuid4(), owner_id)
        now = datetime.now(UTC)
        self.session = Session(
            uuid4(),
            self.principal.account_id,
            _digest(SESSION_TOKEN),
            _digest(CSRF_TOKEN),
            now,
            now + timedelta(hours=1),
            None,
        )

    def authenticate_session(self, token: str) -> AuthenticatedSession | None:
        if token != SESSION_TOKEN:
            return None
        return AuthenticatedSession(self.principal, self.session)


class FakeOfferingService:
    def __init__(self):
        self.records: dict[UUID, ServiceOffering] = {}
        self.calls = []
        self.referenced: set[UUID] = set()

    def create(
        self, principal: Principal, offering: NewServiceOffering
    ) -> ServiceOffering:
        self.calls.append(("create", principal.user_id, offering))
        now = datetime.now(UTC)
        created = ServiceOffering(
            uuid4(), principal.user_id, offering.name, offering.description, now, now
        )
        self.records[created.id] = created
        return created

    def list(self, principal: Principal, *, limit: int, offset: int) -> Page:
        self.calls.append(("list", principal.user_id, limit, offset))
        items = sorted(
            (
                item
                for item in self.records.values()
                if item.user_id == principal.user_id
            ),
            key=lambda item: (item.created_at, item.id),
        )
        return Page(tuple(items[offset : offset + limit]), offset, limit, False)

    def get(self, principal: Principal, offering_id: UUID) -> ServiceOffering:
        self.calls.append(("get", principal.user_id, offering_id))
        return self._owned(principal, offering_id)

    def update(
        self,
        principal: Principal,
        offering_id: UUID,
        changes: ServiceOfferingChanges,
    ) -> ServiceOffering:
        self.calls.append(("update", principal.user_id, offering_id, changes))
        current = self._owned(principal, offering_id)
        updated = ServiceOffering(
            current.id,
            current.user_id,
            changes.values.get("name", current.name),
            changes.values.get("description", current.description),
            current.created_at,
            datetime.now(UTC),
        )
        self.records[offering_id] = updated
        return updated

    def delete(self, principal: Principal, offering_id: UUID) -> None:
        self.calls.append(("delete", principal.user_id, offering_id))
        self._owned(principal, offering_id)
        if offering_id in self.referenced:
            raise ConflictError("offering is referenced")
        del self.records[offering_id]

    def _owned(self, principal: Principal, offering_id: UUID) -> ServiceOffering:
        item = self.records.get(offering_id)
        if item is None or item.user_id != principal.user_id:
            raise NotFoundError("Offering not found")
        return item


def _client(owner_id: UUID, service: FakeOfferingService) -> TestClient:
    app = create_app(
        ManagementConfig("unused", environment="test"),
        authentication_service=FakeAuthentication(owner_id),
        service_offering_service=service,
    )
    app.include_router(router)
    client = TestClient(app)
    client.cookies.set(SESSION_COOKIE, SESSION_TOKEN)
    return client


def _csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": CSRF_TOKEN}


def test_offering_crud_statuses_typed_models_and_bounded_pagination():
    owner_id = uuid4()
    service = FakeOfferingService()
    with _client(owner_id, service) as client:
        created = client.post(
            "/api/v1/offerings",
            json={"name": "Consulting", "description": "Security audit"},
            headers=_csrf_headers(),
        )
        assert created.status_code == 201
        assert created.json()["user_id"] == str(owner_id)
        offering_id = UUID(created.json()["id"])

        fetched = client.get(f"/api/v1/offerings/{offering_id}")
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "Consulting"

        updated = client.patch(
            f"/api/v1/offerings/{offering_id}",
            json={"description": "Updated audit"},
            headers=_csrf_headers(),
        )
        assert updated.status_code == 200
        assert updated.json()["description"] == "Updated audit"

        listed = client.get("/api/v1/offerings?limit=7&offset=2")
        assert listed.status_code == 200
        assert listed.json() == {
            "items": [],
            "limit": 7,
            "offset": 2,
            "has_more": False,
        }
        assert service.calls[-1] == ("list", owner_id, 7, 2)

        oversized_offset = client.get("/api/v1/offerings?offset=9223372036854775808")
        assert oversized_offset.status_code == 422
        assert service.calls[-1] == ("list", owner_id, 7, 2)

        assert client.get("/api/v1/offerings?limit=101").status_code == 422
        assert client.get("/api/v1/offerings?offset=-1").status_code == 422
        deleted = client.delete(
            f"/api/v1/offerings/{offering_id}", headers=_csrf_headers()
        )
        assert deleted.status_code == 204
        assert deleted.content == b""


def test_offering_validation_and_authentication_reject_without_writes():
    service = FakeOfferingService()
    with _client(uuid4(), service) as client:
        invalid_create = client.post(
            "/api/v1/offerings",
            json={"name": " ", "description": "Description"},
            headers=_csrf_headers(),
        )
        unknown_field = client.post(
            "/api/v1/offerings",
            json={
                "name": "Valid",
                "description": "Description",
                "user_id": str(uuid4()),
            },
            headers=_csrf_headers(),
        )
        invalid_patch = client.patch(
            f"/api/v1/offerings/{uuid4()}",
            json={"name": " "},
            headers=_csrf_headers(),
        )
        missing_csrf = client.post(
            "/api/v1/offerings",
            json={"name": "Valid", "description": "Description"},
        )
        assert invalid_create.status_code == 422
        assert unknown_field.status_code == 422
        assert invalid_patch.status_code == 422
        assert missing_csrf.status_code == 403
        assert not [call for call in service.calls if call[0] == "create"]


def test_offering_member_routes_hide_other_owners_and_conflict_on_referenced_delete():
    first_id, second_id = uuid4(), uuid4()
    service = FakeOfferingService()
    client_one = _client(first_id, service)
    client_two = _client(second_id, service)
    try:
        created = client_one.post(
            "/api/v1/offerings",
            json={"name": "Consulting", "description": "Audit"},
            headers=_csrf_headers(),
        )
        offering_id = UUID(created.json()["id"])

        path = f"/api/v1/offerings/{offering_id}"
        assert client_two.get(path).status_code == 404
        assert (
            client_two.patch(
                path, json={"name": "Stolen"}, headers=_csrf_headers()
            ).status_code
            == 404
        )
        assert client_two.delete(path, headers=_csrf_headers()).status_code == 404
        assert client_one.get(path).json()["name"] == "Consulting"

        service.referenced.add(offering_id)
        conflict = client_one.delete(path, headers=_csrf_headers())
        assert conflict.status_code == 409
        assert client_one.get(path).status_code == 200
    finally:
        client_one.close()
        client_two.close()
