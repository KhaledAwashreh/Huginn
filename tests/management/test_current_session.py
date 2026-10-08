import hashlib
import hmac
from dataclasses import replace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from huginn.management.security.tokens import digest_token
from tests.management.test_app_authentication import (
    CSRF_TOKEN,
    NOW,
    SESSION_TOKEN,
    FakeSessions,
    make_app,
)


class BootstrapSessions(FakeSessions):
    def initialize_csrf_digest(
        self, session_id, token_digest, principal, expected_digest, csrf_digest, now
    ):
        if (
            self.row.id != session_id
            or self.row.token_digest != token_digest
            or self.get_active_principal_by_token_digest(token_digest, now) != principal
            or self.row.csrf_digest not in (expected_digest, csrf_digest)
        ):
            return None
        self.row = replace(self.row, csrf_digest=csrf_digest)
        return self.row


def test_bootstrap_returns_identity_and_stable_proof_without_opaque_credential():
    repository = BootstrapSessions()
    app, _, uow = make_app(repository)
    with TestClient(app) as client:
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        first = client.get("/api/v1/sessions/current")
        second = client.get("/api/v1/sessions/current")
        assert first.status_code == 200
        assert first.json() == second.json()
        assert first.json()["account_id"] == str(repository.account_id)
        assert first.json()["user_id"] == str(repository.user_id)
        assert SESSION_TOKEN not in first.text
        assert first.json()["csrf_token"] != CSRF_TOKEN
        assert first.headers["cache-control"] == "no-store"
        assert first.headers["vary"] == "Cookie"
        assert uow.commits == 2
        assert (
            client.delete(
                "/api/v1/sessions/current", headers={"X-CSRF-Token": CSRF_TOKEN}
            ).status_code
            == 403
        )
        assert (
            client.delete(
                "/api/v1/sessions/current",
                headers={"X-CSRF-Token": first.json()["csrf_token"]},
            ).status_code
            == 204
        )


@pytest.mark.parametrize("invalid", ["missing", "expired", "revoked", "disabled"])
def test_invalid_bootstrap_is_generic_and_not_cacheable(invalid):
    repository = BootstrapSessions(
        status="disabled" if invalid == "disabled" else "active"
    )
    if invalid == "expired":
        repository.row = replace(repository.row, expires_at=NOW.replace(year=2000))
    if invalid == "revoked":
        repository.row = replace(repository.row, revoked_at=NOW)
    app, _, _ = make_app(repository)
    with TestClient(app) as client:
        if invalid != "missing":
            client.cookies.set("huginn_management_session", SESSION_TOKEN)
        response = client.get("/api/v1/sessions/current")
    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "authentication_error",
            "message": "Request could not be completed",
            "details": [],
        }
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Cookie"


def test_csrf_derivation_is_versioned_hmac_and_hidden_in_application_values():
    from huginn.management.application.requests.current_session_request import (
        CurrentSessionRequest,
    )
    from huginn.management.application.responses.current_session_response import (
        CurrentSessionResponse,
    )
    from huginn.management.domain.value_objects.common import Principal
    from huginn.management.security.csrf import derive_csrf_token
    from huginn.management.security.csrf_policy import CSRF_CONTEXT_VERSION

    proof = derive_csrf_token(SESSION_TOKEN)
    assert (
        proof
        == hmac.new(
            SESSION_TOKEN.encode(), CSRF_CONTEXT_VERSION.encode(), hashlib.sha256
        ).hexdigest()
    )
    assert proof != derive_csrf_token("another credential")
    assert SESSION_TOKEN not in repr(
        CurrentSessionRequest(Principal(uuid4(), uuid4()), uuid4(), SESSION_TOKEN)
    )
    assert proof not in repr(CurrentSessionResponse(uuid4(), uuid4(), proof, NOW))


@pytest.mark.parametrize(
    "invalid", ["session_id", "principal", "token", "revoked_after_authentication"]
)
def test_service_revalidates_authenticated_input_and_never_commits_invalid_session(
    invalid,
):
    from huginn.management.application.errors.errors import AuthenticationError
    from huginn.management.application.requests.current_session_request import (
        CurrentSessionRequest,
    )
    from huginn.management.application.services.current_session_service import (
        CurrentSessionService,
    )
    from huginn.management.domain.value_objects.common import Principal
    from tests.management.test_app_authentication import FakeUnitOfWork

    repository = BootstrapSessions()
    uow = FakeUnitOfWork()
    reader = CurrentSessionService(
        lambda: uow, sessions_factory=lambda _: repository, clock=lambda: NOW
    )
    request = CurrentSessionRequest(
        Principal(repository.account_id, repository.user_id),
        repository.row.id,
        SESSION_TOKEN,
    )
    if invalid == "session_id":
        request = replace(request, session_id=uuid4())
    elif invalid == "principal":
        request = replace(request, principal=Principal(uuid4(), uuid4()))
    elif invalid == "token":
        request = replace(request, raw_token="invalid")
    else:
        repository.row = replace(repository.row, revoked_at=NOW)
    with pytest.raises(AuthenticationError):
        reader.execute(request)
    assert uow.commits == 0
    assert repository.row.csrf_digest == digest_token(CSRF_TOKEN)


def test_login_http_proof_is_hidden_from_model_repr():
    from huginn.management.presentation.api.responses.authentication import (
        LoginResponse,
    )

    assert "proof-sentinel" not in repr(
        LoginResponse(csrf_token="proof-sentinel", expires_at=NOW)
    )
