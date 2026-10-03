from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.common import Principal
from huginn.management.domain.session import Session
from huginn.management.services.authentication import (
    AuthenticatedSession as ServiceAuthenticatedSession,
)
from huginn.management.services.authentication import (
    IssuedSession,
)

SESSION_TOKEN = "test-session-token"
CSRF_TOKEN = "test-csrf-token"


class FakeReadiness:
    def __init__(self, ready: bool):
        self.ready = ready
        self.calls = 0

    def is_ready(self) -> bool:
        self.calls += 1
        return self.ready


@dataclass
class FakeAuthentication:
    result: IssuedSession | None = None
    login_error: Exception | None = None

    def __post_init__(self):
        self.login_calls = []
        self.logout_calls = []

    def login(self, **kwargs):
        self.login_calls.append(kwargs)
        if self.login_error:
            raise self.login_error
        return self.result

    def authenticate_session(self, token):
        if token != SESSION_TOKEN:
            return None
        now = datetime.now(UTC)
        session = Session(
            uuid4(),
            account_id,
            "unused-token-digest",
            digest(CSRF_TOKEN),
            now,
            now + timedelta(hours=1),
            None,
        )
        return ServiceAuthenticatedSession(Principal(account_id, user_id), session)

    def logout(self, token):
        self.logout_calls.append(token)


def digest(value: str) -> str:
    from hashlib import sha256

    return sha256(value.encode()).hexdigest()


account_id, user_id = uuid4(), uuid4()


def test_app_is_fastapi_and_health_is_process_only():
    readiness = FakeReadiness(False)
    app = create_app(
        ManagementConfig("unused", environment="test"), readiness=readiness
    )
    assert readiness.calls == 0

    with TestClient(app) as client:
        health = client.get("/health")
        assert (health.status_code, health.json()) == (200, {"status": "ok"})
        assert readiness.calls == 0
        ready = client.get("/ready")
        assert (ready.status_code, ready.json()) == (503, {"status": "not_ready"})
        assert readiness.calls == 1


def test_login_sets_cookie_and_returns_csrf_once():
    issued = IssuedSession(
        account_id,
        SESSION_TOKEN,
        CSRF_TOKEN,
        datetime(2099, 10, 3, tzinfo=UTC),
    )
    auth = FakeAuthentication(result=issued)
    config = ManagementConfig(
        "unused",
        cookie_name="management_cookie",
        cookie_secure=True,
        cookie_samesite="Strict",
        session_ttl=timedelta(hours=12),
        environment="production",
    )
    with TestClient(create_app(config, authentication_service=auth)) as client:
        response = client.post(
            "/api/v1/sessions",
            json={"username": "alice", "password": "password-secret"},
        )

    assert response.status_code == 200
    assert response.json() == {
        "csrf_token": CSRF_TOKEN,
        "expires_at": "2099-10-03T00:00:00Z",
    }
    cookie = response.headers["set-cookie"]
    assert "management_cookie=" + SESSION_TOKEN in cookie
    assert "Path=/" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "SameSite=Strict" in cookie and "Max-Age=43200" in cookie
    assert auth.login_calls == [
        {
            "username": "alice",
            "password": "password-secret",
            "client_ip": "testclient",
        }
    ]


def test_login_validation_is_native_and_does_not_echo_password():
    with TestClient(
        create_app(ManagementConfig("unused", environment="test"))
    ) as client:
        response = client.post(
            "/api/v1/sessions",
            json={"username": "alice", "password": "secret-sentinel", "extra": 1},
        )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body"]
    assert "secret-sentinel" not in response.text
    assert "input" not in response.text


def test_logout_checks_csrf_and_revokes_through_authentication_service():
    auth = FakeAuthentication()
    with TestClient(
        create_app(
            ManagementConfig("unused", environment="test"), authentication_service=auth
        )
    ) as client:
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        denied = client.delete("/api/v1/sessions/current")
        assert denied.status_code == 403
        assert auth.logout_calls == []

        logged_out = client.delete(
            "/api/v1/sessions/current",
            headers={"X-CSRF-Token": CSRF_TOKEN},
        )
    assert logged_out.status_code == 204
    assert auth.logout_calls == [SESSION_TOKEN]
    assert "Max-Age=0" in logged_out.headers["set-cookie"]
    assert "HttpOnly" in logged_out.headers["set-cookie"]


def test_custom_cookie_name_does_not_accept_default_cookie():
    auth = FakeAuthentication()
    config = ManagementConfig(
        "unused", cookie_name="custom_management_session", environment="test"
    )
    with TestClient(create_app(config, authentication_service=auth)) as client:
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        response = client.delete(
            "/api/v1/sessions/current", headers={"X-CSRF-Token": CSRF_TOKEN}
        )

    assert response.status_code == 401
    assert auth.logout_calls == []
