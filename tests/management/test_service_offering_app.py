from datetime import UTC, datetime, timedelta
from uuid import uuid4

from huginn.management.domain import ConflictError, NotFoundError, Principal, Session
from huginn.management.identity import SessionService
from tests.management.test_app_authentication import make_app


class Sessions:
    def __init__(self):
        self.values = {}
        for token, csrf in (("one", "csrf-one"), ("two", "csrf-two")):
            account, user = uuid4(), uuid4()
            session = Session(
                uuid4(),
                account,
                SessionService.digest(token),
                SessionService.digest(csrf),
                datetime.now(UTC),
                datetime.now(UTC) + timedelta(hours=1),
                None,
            )
            self.values[token] = (session, Principal(account, user), csrf)

    def get_by_token_digest(self, digest):
        return next(
            (s for s, _, _ in self.values.values() if s.token_digest == digest), None
        )

    def get_active_principal_by_token_digest(self, digest, now):
        return next(
            (
                p
                for s, p, _ in self.values.values()
                if s.token_digest == digest and s.expires_at > now
            ),
            None,
        )


class Offerings:
    def __init__(self):
        self.calls = []

    def create(self, principal, body):
        self.calls.append(("create", principal.user_id, body))
        return {
            "id": str(uuid4()),
            "user_id": str(principal.user_id),
            "name": body.name,
            "description": body.description,
        }

    def list(self, principal, *, limit, offset):
        self.calls.append(("list", principal.user_id, limit, offset))
        return {"items": [], "limit": limit, "offset": offset, "has_more": False}

    def get(self, principal, offering_id):
        self.calls.append(("get", principal.user_id, offering_id))
        raise NotFoundError("not found")

    def update(self, principal, offering_id, patch):
        self.calls.append(("patch", principal.user_id, offering_id, patch))
        if str(offering_id).endswith("0001"):
            raise NotFoundError("not found")
        return {
            "id": str(offering_id),
            "user_id": str(principal.user_id),
            "name": patch.name or "Consulting",
            "description": patch.description or "Audit",
        }

    def delete(self, principal, offering_id):
        self.calls.append(("delete", principal.user_id, offering_id))
        if str(offering_id).endswith("0002"):
            raise ConflictError("referenced")


def test_offering_routes_use_authenticated_owner_require_csrf_and_map_statuses():
    sessions, service = Sessions(), Offerings()
    app, _, _ = make_app(sessions, service_offering_service=service)
    client = app.test_client()
    owners = {
        principal.user_id for _session, principal, _csrf in sessions.values.values()
    }
    for token, (_session, principal, csrf) in sessions.values.items():
        client.set_cookie("huginn_management_session", token)
        created = client.post(
            "/api/v1/offerings",
            json={"name": "Consulting", "description": "Audit"},
            headers={"X-CSRF-Token": csrf},
        )
        assert created.status_code == 201 and created.json["user_id"] == str(
            principal.user_id
        )
        listing = client.get("/api/v1/offerings?limit=7&offset=2")
        assert listing.status_code == 200 and service.calls[-1] == (
            "list",
            principal.user_id,
            7,
            2,
        )
    offering_id = uuid4()
    token, (session, principal, csrf) = next(iter(sessions.values.items()))
    client.set_cookie("huginn_management_session", token)
    assert client.get(f"/api/v1/offerings/{offering_id}").status_code == 404
    assert (
        client.patch(
            f"/api/v1/offerings/{offering_id}",
            json={"name": "Changed"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            "/api/v1/offerings/00000000-0000-0000-0000-000000000001",
            json={"name": "Changed"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 404
    )
    assert (
        client.delete(
            f"/api/v1/offerings/{offering_id}", headers={"X-CSRF-Token": csrf}
        ).status_code
        == 204
    )
    assert (
        client.delete(
            "/api/v1/offerings/00000000-0000-0000-0000-000000000002",
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/offerings",
            json={"name": " ", "description": "Audit"},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 422
    )
    assert len([call for call in service.calls if call[0] == "create"]) == 2
    assert (
        client.post(
            "/api/v1/offerings",
            json={"name": "Valid", "description": "Audit", "user_id": str(uuid4())},
            headers={"X-CSRF-Token": csrf},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/offerings", json={"name": "Valid", "description": "Audit"}
        ).status_code
        == 403
    )
    assert len([call for call in service.calls if call[0] == "create"]) == 2
    assert client.get("/api/v1/offerings?limit=101").status_code == 422
    assert all(
        call[1] in owners
        for call in service.calls
        if call[0] in {"create", "list", "get", "patch", "delete"}
    )


def test_two_user_routes_hide_cross_owner_offering_on_every_member_method():
    class OwnerScopedOfferings:
        def __init__(self):
            self.records = {}

        def create(self, principal, body):
            offering_id = uuid4()
            record = {
                "id": str(offering_id),
                "user_id": str(principal.user_id),
                "name": body.name,
                "description": body.description,
            }
            self.records[offering_id] = record
            return record

        def get(self, principal, offering_id):
            record = self.records.get(offering_id)
            if record is None or record["user_id"] != str(principal.user_id):
                raise NotFoundError("not found")
            return record

        def update(self, principal, offering_id, patch):
            record = self.get(principal, offering_id)
            record.update(patch.model_dump(exclude_unset=True))
            return record

        def delete(self, principal, offering_id):
            self.get(principal, offering_id)
            del self.records[offering_id]

    sessions = Sessions()
    offerings = OwnerScopedOfferings()
    app, _, _ = make_app(sessions, service_offering_service=offerings)
    client = app.test_client()
    first, second = list(sessions.values.items())
    first_token, (_, first_principal, first_csrf) = first
    second_token, (_, second_principal, second_csrf) = second
    assert first_principal.user_id != second_principal.user_id

    client.set_cookie("huginn_management_session", first_token)
    created = client.post(
        "/api/v1/offerings",
        json={"name": "Consulting", "description": "Audit"},
        headers={"X-CSRF-Token": first_csrf},
    )
    assert created.status_code == 201
    path = f"/api/v1/offerings/{created.json['id']}"
    assert client.get(path).status_code == 200

    client.set_cookie("huginn_management_session", second_token)
    assert client.get(path).status_code == 404
    assert (
        client.patch(
            path,
            json={"name": "Stolen"},
            headers={"X-CSRF-Token": second_csrf},
        ).status_code
        == 404
    )
    assert client.delete(path, headers={"X-CSRF-Token": second_csrf}).status_code == 404

    client.set_cookie("huginn_management_session", first_token)
    assert client.get(path).json["name"] == "Consulting"
    assert client.delete(path, headers={"X-CSRF-Token": first_csrf}).status_code == 204
