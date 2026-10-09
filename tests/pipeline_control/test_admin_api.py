from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig


def test_admin_pipeline_routes_require_authentication_and_are_private():
    client = TestClient(create_app(ManagementConfig(database_url="unused")))
    prefix = "/api/v1/admin/pipeline/invocations"
    for suffix in (
        "",
        "/00000000-0000-0000-0000-000000000001",
        "/00000000-0000-0000-0000-000000000001/events",
        "/00000000-0000-0000-0000-000000000001/companies",
    ):
        response = client.get(prefix + suffix)
        assert response.status_code == 401
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["vary"] == "Cookie"
    response = client.post(
        prefix, json={"request_id": "00000000-0000-0000-0000-000000000002"}
    )
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


def test_admin_contract_csrf_paging_and_safe_failures():
    from datetime import UTC, datetime, timedelta
    from types import SimpleNamespace
    from uuid import UUID

    from huginn.management.domain.entities.session import Session
    from huginn.management.domain.value_objects.account_role import AccountRole
    from huginn.management.security.tokens import digest_token
    from huginn.pipeline_control.application.errors.invocation import (
        InvocationNotFoundError,
    )
    from huginn.pipeline_control.application.errors.trigger import TriggerRateLimitError
    from huginn.pipeline_control.application.responses.list_invocations_response import (
        ListInvocationsResponse,
    )
    from huginn.pipeline_control.application.responses.trigger_invocation_response import (
        TriggerInvocationResponse,
    )
    from huginn.pipeline_control.domain.errors.invocation import (
        ActiveInvocationConflictError,
    )

    now = datetime.now(UTC)
    account_id = UUID(int=1)
    invocation_id = UUID(int=3)
    principal = SimpleNamespace(role=AccountRole("user"), account_id=account_id)
    session = Session(
        UUID(int=2),
        account_id,
        digest_token("session"),
        digest_token("csrf"),
        now,
        now + timedelta(hours=1),
        None,
    )
    auth = SimpleNamespace(
        authenticate_session=lambda _: SimpleNamespace(
            principal=principal, session=session
        )
    )
    received = []

    def execute(request):
        received.append(request)
        return TriggerInvocationResponse(invocation_id, "queued", now, True)

    def history(request):
        received.append(request)
        return ListInvocationsResponse((), request.limit, request.offset, False)

    services = SimpleNamespace(
        trigger=SimpleNamespace(execute=execute),
        history=SimpleNamespace(execute=history),
    )
    app = create_app(
        ManagementConfig("unused"),
        authentication_service=auth,
        pipeline_services=services,
    )
    client = TestClient(app)
    client.cookies.set("huginn_management_session", "session")
    prefix = "/api/v1/admin/pipeline/invocations"
    assert client.get(prefix).status_code == 403
    principal.role = AccountRole("admin")
    body = {"request_id": str(UUID(int=4))}
    assert client.post(prefix, json=body).status_code == 403
    assert received == []
    response = client.post(prefix, json=body, headers={"X-CSRF-Token": "csrf"})
    assert response.status_code == 202
    assert response.headers["location"] == prefix + "/" + str(invocation_id)
    assert set(response.json()) == {"id", "status", "requested_at"}
    assert received[-1].requester_account_id == account_id
    assert (
        client.post(
            prefix, json={**body, "role": "admin"}, headers={"X-CSRF-Token": "csrf"}
        ).status_code
        == 422
    )
    response = client.get(prefix + "?limit=100&offset=150&state=failed")
    assert response.status_code == 200
    assert (received[-1].limit, received[-1].offset, received[-1].state) == (
        100,
        150,
        "failed",
    )
    for query in ("limit=101", "offset=-1", "state=nonsense", "unknown=secret"):
        response = client.get(prefix + "?" + query)
        assert response.status_code == 422
        assert response.headers["cache-control"] == "no-store"
        assert "secret" not in response.text

    def fail(error):
        def execute(_):
            raise error

        return SimpleNamespace(execute=execute)

    services.trigger = fail(ActiveInvocationConflictError(str(invocation_id)))
    response = client.post(prefix, json=body, headers={"X-CSRF-Token": "csrf"})
    assert response.status_code == 409
    assert response.json()["error"]["details"] == [
        {"active_invocation_id": str(invocation_id)}
    ]
    services.trigger = fail(TriggerRateLimitError(120))
    response = client.post(prefix, json=body, headers={"X-CSRF-Token": "csrf"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "120"
    services.get = fail(InvocationNotFoundError("private-error-text"))
    response = client.get(prefix + "/" + str(invocation_id))
    assert response.status_code == 404
    assert "private-error-text" not in response.text
    services.get = fail(RuntimeError("private-error-text"))
    response = client.get(prefix + "/" + str(invocation_id))
    assert response.status_code == 500
    assert response.headers["cache-control"] == "no-store"
    assert "private-error-text" not in response.text
    principal.role = AccountRole("user")
    assert client.get(prefix).status_code == 403


def test_live_session_promotion_demotion_and_durable_api_receipt(
    integration_database_url,
):
    from uuid import uuid4

    import psycopg

    from huginn.management.app import create_account_administration_services
    from huginn.management.application.commands.provisioning import ProvisionIdentity
    from huginn.management.application.requests.assign_account_role_request import (
        AssignAccountRoleRequest,
    )
    from huginn.management.domain.value_objects.account_role import AccountRole

    config = ManagementConfig(integration_database_url, environment="test")
    administration = create_account_administration_services(config)
    username = f"pipeline-admin-{uuid4()}"
    password = "pipeline-test-correct-horse-battery"
    identity = administration.provisioning.provision(
        ProvisionIdentity(
            username,
            "Admin",
            "Test",
            f"{uuid4()}@example.test",
            "+12025550123",
            "US",
            "UTC",
            password,
        )
    )
    prefix = "/api/v1/admin/pipeline/invocations"
    try:
        client = TestClient(create_app(config))
        login = client.post(
            "/api/v1/sessions", json={"username": username, "password": password}
        )
        assert login.status_code == 200
        csrf = {"X-CSRF-Token": login.json()["csrf_token"]}
        assert client.get("/api/v1/sessions/current").json()["role"] == "user"
        assert client.get(prefix).status_code == 403
        administration.role_assignment.execute(
            AssignAccountRoleRequest(username, AccountRole("admin"))
        )
        assert client.get("/api/v1/sessions/current").json()["role"] == "admin"
        request = {"request_id": str(uuid4())}
        accepted = client.post(prefix, json=request, headers=csrf)
        assert accepted.status_code == 202
        assert client.post(prefix, json=request, headers=csrf).json() == accepted.json()
        detail = client.get(accepted.headers["location"])
        assert detail.status_code == 200
        assert detail.json()["requester_account_id"] == str(identity.account_id)
        assert len(detail.json()["stages"]) == 9
        assert (
            client.get(accepted.headers["location"] + "/companies").json()[
                "tracking_state"
            ]
            == "tracked"
        )
        administration.role_assignment.execute(
            AssignAccountRoleRequest(username, AccountRole("user"))
        )
        assert client.get(prefix).status_code == 403
        assert client.get("/api/v1/sessions/current").json()["role"] == "user"
    finally:
        with psycopg.connect(integration_database_url) as connection:
            connection.execute(
                "DELETE FROM ops.pipeline_invocation_events WHERE invocation_id IN (SELECT id FROM ops.pipeline_invocations WHERE requester_account_id=%s)",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM ops.pipeline_invocations WHERE requester_account_id=%s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.sessions WHERE account_id=%s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.professional_profiles WHERE user_id=%s",
                (identity.user_id,),
            )
            connection.execute(
                "DELETE FROM operational.users WHERE account_id=%s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.account_recovery_identity WHERE account_id=%s",
                (identity.account_id,),
            )
            connection.execute(
                "DELETE FROM operational.accounts WHERE id=%s", (identity.account_id,)
            )
