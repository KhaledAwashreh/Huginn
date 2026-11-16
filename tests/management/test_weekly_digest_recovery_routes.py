from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.session import Session
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)
from huginn.management.security.tokens import digest_token


@pytest.mark.parametrize("outcome", ["sent", "failed"])
def test_recovery_response_is_private_and_contains_only_the_recorded_outcome(outcome):
    principal = Principal(uuid4(), uuid4())
    now = datetime.now(UTC)
    delivery_id = uuid4()
    accepted_at = now if outcome == "sent" else None

    class Recovery:
        def execute(self, actor, request):
            assert actor == principal
            assert request.delivery_id == delivery_id
            return SimpleNamespace(
                id=delivery_id,
                state=outcome,
                version=5,
                accepted_at=accepted_at,
                settled_at=now,
                body="private content",
                recipient="private@example.test",
            )

    app = create_app(
        ManagementConfig("unused", environment="test"),
        recover_weekly_digest_service=Recovery(),
    )
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    with TestClient(app) as client:
        response = client.post(
            f"/api/v1/weekly-digests/{delivery_id}/recovery",
            json={
                "outcome": outcome,
                "reason": "Transport evidence checked",
                "accepted_at": accepted_at.isoformat() if accepted_at else None,
            },
            headers={"X-CSRF-Token": "csrf"},
        )
    assert response.status_code == 200, response.text
    result = response.json()
    assert set(result) == {"id", "state", "version", "accepted_at", "settled_at"}
    assert result["state"] == outcome
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Cookie"
    assert "private" not in response.text


def test_recovery_requires_csrf_and_uses_only_the_authenticated_actor():
    observed = []

    class Recovery:
        def execute(self, principal, request):
            observed.append((principal, request))
            raise NotFoundError("Weekly digest not found")

    principal = Principal(uuid4(), uuid4())
    now = datetime.now(UTC)
    app = create_app(
        ManagementConfig("unused", environment="test"),
        recover_weekly_digest_service=Recovery(),
    )
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    delivery_id = uuid4()
    path = f"/api/v1/weekly-digests/{delivery_id}/recovery"
    body = {
        "outcome": "sent",
        "reason": "Verified SMTP acceptance",
        "accepted_at": now.isoformat(),
    }
    with TestClient(app) as client:
        assert client.post(path, json=body).status_code == 403
        assert observed == []
        response = client.post(path, json=body, headers={"X-CSRF-Token": "csrf"})
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["vary"] == "Cookie"
        assert len(observed) == 1
        assert observed[0][0] == principal
        assert observed[0][1].delivery_id == delivery_id
        assert observed[0][1].accepted_at == now
        for changes in (
            {"business_id": str(uuid4())},
            {"actor_user_id": str(uuid4())},
            {"accepted_at": None},
            {"accepted_at": "2026-11-15T10:00:00"},
            {"outcome": "failed"},
            {"reason": "   "},
        ):
            response = client.post(
                path, json={**body, **changes}, headers={"X-CSRF-Token": "csrf"}
            )
            assert response.status_code == 422, response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["vary"] == "Cookie"
        assert len(observed) == 1
