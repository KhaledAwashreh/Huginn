from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.session import Session
from huginn.management.domain.value_objects.common import Page, Principal
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)
from huginn.management.security.tokens import digest_token
from huginn.management.weekly_digest_bootstrap import create_weekly_digest_service


def test_rollback_disables_generation_and_presentation_but_keeps_retained_reads_available():
    calls = []

    class NoWrites:
        def execute(self, *_):
            calls.append(True)
            raise AssertionError("Disabled discovery must not call a writer")

    class Reads:
        def list_recommendations(self, principal, request, **filters):
            return Page((), request.offset, request.limit, False)

    app = create_app(
        ManagementConfig(
            "unused", environment="test", discovery_new_work_enabled=False
        ),
        recommendation_generation_service=NoWrites(),
        prepare_recommendation_offer_service=NoWrites(),
        confirm_recommendation_offer_service=NoWrites(),
        prospecting_read_service=Reads(),
    )
    principal = Principal(uuid4(), uuid4())
    now = datetime.now(UTC)
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    with TestClient(app) as client:
        for path, body in (
            ("/api/v1/recommendations", {"strategy_id": str(uuid4()), "limit": 10}),
            (
                f"/api/v1/recommendations/{uuid4()}/offer-preparations",
                {"assessment_revision_id": str(uuid4()), "request_key": "rollback"},
            ),
            (
                f"/api/v1/recommendations/offer-preparations/{uuid4()}/confirm",
                {"claim_token": "existing-claim"},
            ),
        ):
            response = client.post(path, json=body, headers={"X-CSRF-Token": "csrf"})
            assert response.status_code == 503, response.text
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["vary"] == "Cookie"
        assert client.get("/api/v1/recommendations").status_code == 200
    assert calls == []


def test_disabled_scheduled_composition_refuses_new_work_before_any_database_access():
    with pytest.raises(ValueError, match="disabled"):
        create_weekly_digest_service(
            ManagementConfig("unused", discovery_new_work_enabled=False)
        )
