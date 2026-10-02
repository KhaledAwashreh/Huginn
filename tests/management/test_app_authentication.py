from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from huginn.management import app as app_module
from huginn.management.config import ManagementConfig
from huginn.management.discovery_strategies import ClientDiscoveryStrategyService
from huginn.management.domain import (
    AuthenticationError,
    Principal,
    RateLimitError,
    Session,
)
from huginn.management.ideal_client_profiles import IdealClientProfileService
from huginn.management.identity import IssuedSession, SessionService
from huginn.management.service_offerings import ServiceOfferingService

SESSION_TOKEN = "raw-session-token-sentinel"
CSRF_TOKEN = "raw-csrf-token-sentinel"
NOW = datetime(2099, 10, 2, tzinfo=UTC)


class FakeUnitOfWork:
    def __init__(self):
        self.connection = object()
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1


class FakeSessions:
    def __init__(self, *, status="active"):
        self.account_id, self.user_id = uuid4(), uuid4()
        self.row = Session(
            uuid4(),
            self.account_id,
            SessionService.digest(SESSION_TOKEN),
            SessionService.digest(CSRF_TOKEN),
            NOW,
            NOW + timedelta(hours=1),
            None,
        )
        self.status = status
        self.calls = []

    def get_by_token_digest(self, digest):
        self.calls.append(("session", digest))
        return self.row if self.row.token_digest == digest else None

    def get_active_principal_by_token_digest(self, digest, now):
        self.calls.append(("principal", digest))
        if (
            self.row.token_digest == digest
            and self.row.revoked_at is None
            and self.row.expires_at > now
            and self.status == "active"
        ):
            return Principal(self.account_id, self.user_id)
        return None

    def revoke_current(self, session_id, revoked_at):
        self.row = replace(self.row, revoked_at=revoked_at)


class FakeLogin:
    def __init__(self, result=None, error=None):
        self.result, self.error, self.calls = result, error, []

    def login(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result


class FakePasswordChange:
    def __init__(self, error=None):
        self.error, self.calls = error, []

    def change_password(self, account_id, **kwargs):
        self.calls.append((account_id, kwargs))
        if self.error:
            raise self.error


def make_app(
    sessions=None,
    *,
    login=None,
    password_change=None,
    user_profile_service=None,
    service_offering_service=None,
    ideal_client_profile_service=None,
    discovery_strategy_service=None,
    config=None,
):
    repository = sessions or FakeSessions()
    uow = FakeUnitOfWork()
    app = app_module.create_app(
        config or ManagementConfig("unused", environment="test"),
        readiness=type("Ready", (), {"is_ready": lambda self: True})(),
        unit_of_work_factory=lambda: uow,
        sessions_factory=lambda _uow: repository,
        login_service=login,
        password_change_service=password_change,
        user_profile_service=user_profile_service,
        service_offering_service=service_offering_service,
        ideal_client_profile_service=ideal_client_profile_service,
        discovery_strategy_service=discovery_strategy_service,
        clock=lambda: datetime.now(UTC),
    )
    return app, repository, uow


def register_protected_read(app):
    from flask import g

    @app.get("/protected-test")
    @app_module.authenticated
    def protected():
        return {
            "account_id": str(g.principal.account_id),
            "user_id": str(g.principal.user_id),
        }


@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/offerings?offset=" + "9" * 5000,
        "/api/v1/ideal-client-profiles?offset=" + "9" * 5000,
        "/api/v1/discovery-strategies?offset=" + "9" * 5000,
    ),
)
def test_oversized_decimal_list_offsets_return_validation_errors(path):
    app, _, _ = make_app()
    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)

    response = client.get(path)

    assert response.status_code == 422
    assert response.json["error"]["code"] == "validation_error"
    assert response.json["error"]["details"][0]["loc"] == ["offset"]


@pytest.mark.parametrize(
    ("path", "service_type", "service_arg"),
    (
        ("/api/v1/offerings", ServiceOfferingService, "service_offering_service"),
        (
            "/api/v1/ideal-client-profiles",
            IdealClientProfileService,
            "ideal_client_profile_service",
        ),
        (
            "/api/v1/discovery-strategies",
            ClientDiscoveryStrategyService,
            "discovery_strategy_service",
        ),
    ),
)
def test_postgres_unrepresentable_offsets_return_empty_pages(
    path, service_type, service_arg
):
    def fail_if_queried():
        pytest.fail("unrepresentable offsets must not open a unit of work")

    service = service_type(fail_if_queried)
    app, _, _ = make_app(**{service_arg: service})
    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)

    response = client.get(f"{path}?offset=9223372036854775808")

    assert response.status_code == 200
    assert response.json == {
        "items": [],
        "offset": 9223372036854775808,
        "limit": 50,
        "has_more": False,
    }


@pytest.mark.parametrize(
    "case", ["missing", "invalid", "expired", "revoked", "disabled"]
)
def test_authentication_rejects_bad_cookie_states(case):
    sessions = FakeSessions(status="disabled" if case == "disabled" else "active")
    if case == "expired":
        sessions.row = replace(
            sessions.row,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            expires_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
    elif case == "revoked":
        sessions.row = replace(sessions.row, revoked_at=NOW)
    app, _, _ = make_app(sessions)
    register_protected_read(app)
    client = app.test_client()
    if case != "missing":
        client.set_cookie(
            "huginn_management_session",
            "wrong-session-token" if case == "invalid" else SESSION_TOKEN,
        )

    response = client.get("/protected-test")

    assert response.status_code == 401
    assert response.json["error"]["code"] == "authentication_error"


def test_safe_read_returns_principal_resolved_from_session():
    app, sessions, _ = make_app()
    register_protected_read(app)
    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)

    response = client.get("/protected-test")

    assert response.status_code == 200
    assert response.json == {
        "account_id": str(sessions.account_id),
        "user_id": str(sessions.user_id),
    }


@pytest.mark.parametrize("method", ["POST", "PATCH", "PUT", "DELETE"])
@pytest.mark.parametrize("csrf", [None, "wrong-csrf-token"])
def test_unsafe_methods_reject_missing_or_wrong_csrf_before_handler(method, csrf):
    app, _, _ = make_app()
    entered = []

    @app.route("/protected-test", methods=[method])
    @app_module.authenticated
    def protected():
        entered.append(True)
        return {"ok": True}

    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)
    headers = {} if csrf is None else {"X-CSRF-Token": csrf}

    response = client.open("/protected-test", method=method, headers=headers)

    assert response.status_code == 403
    assert response.json["error"]["code"] == "authorization_error"
    assert entered == []


def test_payload_ownership_identifier_cannot_override_resolved_principal():
    from flask import g, request

    app, sessions, _ = make_app()

    @app.post("/protected-test")
    @app_module.authenticated
    def protected():
        return {
            "owner_id": str(g.principal.user_id),
            "payload_id": request.json["user_id"],
        }

    other_user_id = str(uuid4())
    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)
    response = client.post(
        "/protected-test",
        json={"user_id": other_user_id},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )

    assert response.status_code == 200
    assert response.json == {
        "owner_id": str(sessions.user_id),
        "payload_id": other_user_id,
    }


def test_login_sets_http_only_configured_cookie_and_returns_csrf_once():
    issued = IssuedSession(
        uuid4(), SESSION_TOKEN, CSRF_TOKEN, datetime(2099, 10, 3, tzinfo=UTC)
    )
    login = FakeLogin(issued)
    config = ManagementConfig(
        "unused",
        cookie_name="management_cookie",
        cookie_secure=True,
        cookie_samesite="Strict",
        session_ttl=timedelta(hours=12),
        environment="production",
    )
    app, _, _ = make_app(login=login, config=config)

    response = app.test_client().post(
        "/api/v1/sessions", json={"username": "alice", "password": "plain-password"}
    )

    assert response.status_code == 200
    assert response.json == {
        "csrf_token": CSRF_TOKEN,
        "expires_at": issued.expires_at.isoformat(),
    }
    cookie = response.headers["Set-Cookie"]
    assert "management_cookie=" + SESSION_TOKEN in cookie
    assert "Path=/" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "SameSite=Strict" in cookie and "Max-Age=43200" in cookie
    assert login.calls == [
        {"username": "alice", "password": "plain-password", "client_ip": "127.0.0.1"}
    ]


@pytest.mark.parametrize("secure", [False, True])
def test_local_and_production_cookie_secure_setting_is_respected(secure):
    issued = IssuedSession(
        uuid4(), SESSION_TOKEN, CSRF_TOKEN, datetime(2099, 10, 3, tzinfo=UTC)
    )
    config = ManagementConfig(
        "unused",
        cookie_secure=secure,
        environment="test" if not secure else "production",
    )
    app, _, _ = make_app(login=FakeLogin(issued), config=config)
    response = app.test_client().post(
        "/api/v1/sessions", json={"username": "alice", "password": "plain-password"}
    )
    assert response.status_code == 200
    assert ("Secure" in response.headers["Set-Cookie"]) is secure


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (AuthenticationError("invalid username or password"), 401),
        (RateLimitError("temporarily limited"), 429),
    ],
)
def test_login_errors_are_safe_and_have_no_cookie(error, status):
    app, _, _ = make_app(login=FakeLogin(error=error))
    response = app.test_client().post(
        "/api/v1/sessions",
        json={"username": "alice", "password": "plain-password-secret"},
    )
    assert response.status_code == status
    assert response.json["error"]["message"] == "Request could not be completed"
    assert "Set-Cookie" not in response.headers
    assert "plain-password-secret" not in response.get_data(as_text=True)


def test_logout_revokes_session_and_deletes_cookie():
    app, sessions, _ = make_app()
    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)

    response = client.delete(
        "/api/v1/sessions/current", headers={"X-CSRF-Token": CSRF_TOKEN}
    )

    assert response.status_code == 204
    assert sessions.row.revoked_at is not None
    assert response.headers["Set-Cookie"].startswith("huginn_management_session=")
    assert "Max-Age=0" in response.headers["Set-Cookie"]
    assert "Path=/" in response.headers["Set-Cookie"]
    assert "HttpOnly" in response.headers["Set-Cookie"]


def test_password_change_uses_resolved_account_and_deletes_cookie():
    password_change = FakePasswordChange()
    app, sessions, _ = make_app(password_change=password_change)
    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)

    response = client.patch(
        "/api/v1/me/password",
        json={
            "current_password": "current-password",
            "new_password": "replacement-password",
        },
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )

    assert response.status_code == 204
    assert password_change.calls == [
        (
            sessions.account_id,
            {
                "current_password": "current-password",
                "new_password": "replacement-password",
            },
        )
    ]
    assert "Max-Age=0" in response.headers["Set-Cookie"]


def test_wrong_current_password_is_generic_authentication_error():
    app, _, _ = make_app(
        password_change=FakePasswordChange(
            AuthenticationError("wrong current password sentinel")
        )
    )
    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)
    response = client.patch(
        "/api/v1/me/password",
        json={
            "current_password": "current-password",
            "new_password": "replacement-password",
        },
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert response.status_code == 401
    assert response.json["error"]["message"] == "Request could not be completed"
    assert "wrong current password sentinel" not in response.get_data(as_text=True)


def test_failure_responses_and_logs_redact_all_authentication_sentinels(caplog):
    import logging

    password = "plaintext-password-sentinel"
    password_hash = "stored-password-hash-sentinel"
    token_digest = SessionService.digest(SESSION_TOKEN)
    csrf_digest = SessionService.digest(CSRF_TOKEN)
    sentinels = (
        password,
        password_hash,
        SESSION_TOKEN,
        token_digest,
        CSRF_TOKEN,
        csrf_digest,
    )
    caplog.set_level(logging.DEBUG)

    login_app, _, _ = make_app(login=FakeLogin(error=RuntimeError(" ".join(sentinels))))
    login = login_app.test_client().post(
        "/api/v1/sessions", json={"username": "alice", "password": password}
    )
    assert login.status_code == 500

    change_app, _, _ = make_app(
        password_change=FakePasswordChange(RuntimeError(" ".join(sentinels)))
    )
    client = change_app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)
    changed = client.patch(
        "/api/v1/me/password",
        json={"current_password": password, "new_password": "replacement-password"},
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert changed.status_code == 500

    responses = [login, changed]

    for case in ("missing", "invalid", "expired", "revoked", "disabled"):
        sessions = FakeSessions(status="disabled" if case == "disabled" else "active")
        if case == "expired":
            sessions.row = replace(
                sessions.row, expires_at=datetime(2020, 1, 1, tzinfo=UTC)
            )
        elif case == "revoked":
            sessions.row = replace(sessions.row, revoked_at=NOW)
        app, _, _ = make_app(sessions)
        register_protected_read(app)
        client = app.test_client()
        if case != "missing":
            client.set_cookie(
                "huginn_management_session",
                "wrong-session-token" if case == "invalid" else SESSION_TOKEN,
            )
        responses.append(client.get("/protected-test"))

    for csrf in (None, "wrong-csrf-token"):
        app, _, _ = make_app()

        @app.post("/protected-csrf-test")
        @app_module.authenticated
        def csrf_failure_route():
            return {"ok": True}

        client = app.test_client()
        client.set_cookie("huginn_management_session", SESSION_TOKEN)
        headers = {} if csrf is None else {"X-CSRF-Token": csrf}
        responses.append(client.post("/protected-csrf-test", headers=headers))

    failed_login_app, _, _ = make_app(
        login=FakeLogin(error=AuthenticationError("invalid username or password"))
    )
    responses.append(
        failed_login_app.test_client().post(
            "/api/v1/sessions",
            json={"username": "alice", "password": password},
        )
    )
    throttled_app, _, _ = make_app(
        login=FakeLogin(error=RateLimitError("temporarily limited"))
    )
    responses.append(
        throttled_app.test_client().post(
            "/api/v1/sessions",
            json={"username": "alice", "password": password},
        )
    )
    evidence = "\n".join(
        [response.get_data(as_text=True) for response in responses] + [caplog.text]
    )
    for sentinel in sentinels:
        assert sentinel not in evidence
