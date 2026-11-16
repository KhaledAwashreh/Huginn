"""HTTP routing remains a scoped, private, side-effect-free read boundary."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.session import Session
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import Page, Principal
from huginn.management.presentation.api.dependencies.authentication import (
    AuthenticatedSession,
    get_authenticated_session,
)


def read_client(service):
    principal = Principal(uuid4(), uuid4())
    now = datetime.now(UTC)
    app = create_app(
        ManagementConfig("unused", environment="test"),
        prospecting_read_service=service,
    )
    session = Session(uuid4(), principal.account_id, "digest", "csrf", now, now, None)
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    return TestClient(app), principal


@pytest.mark.parametrize(
    ("path", "method", "filter_name", "filter_value"),
    [
        ("recommendations", "list_recommendations", "status", "rejected"),
        ("prospects", "list_prospects", "stage", "closed"),
        ("suppressions", "list_manageable_suppressions", None, None),
    ],
)
def test_lists_pass_literal_search_and_pagination_to_scoped_service(
    path, method, filter_name, filter_value
):
    observed = []

    class Reads:
        pass

    def read(principal, request, **filters):
        observed.append((principal, request, filters))
        return Page((), request.offset, request.limit, False)

    service = Reads()
    setattr(service, method, read)
    client, principal = read_client(service)
    params = {"search": "Acme_%", "offset": 40, "limit": 10}
    if filter_name:
        params[filter_name] = filter_value
    with client:
        response = client.get(f"/api/v1/{path}", params=params)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "items": [],
        "offset": 40,
        "limit": 10,
        "has_more": False,
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Cookie"
    assert observed[0][0] == principal
    assert observed[0][1].search == "Acme_%"
    if filter_name:
        assert observed[0][2][filter_name].value == filter_value


@pytest.mark.parametrize("path", ["recommendations", "prospects", "suppressions"])
def test_invalid_list_inputs_are_private_and_do_not_reach_services(path):
    client, _ = read_client(object())
    with client:
        for params in ({"limit": 0}, {"offset": -1}, {"search": "a" * 201}):
            response = client.get(f"/api/v1/{path}", params=params)
            assert response.status_code == 422
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["vary"] == "Cookie"


def test_exact_revision_selector_is_forwarded_and_missing_identity_is_private():
    rec_id, revision_id = uuid4(), uuid4()
    observed = []

    class Reads:
        def get_recommendation(
            self, principal, requested_id, *, assessment_revision_id
        ):
            observed.append((principal, requested_id, assessment_revision_id))
            raise NotFoundError("Recommendation not found")

    client, principal = read_client(Reads())
    with client:
        response = client.get(
            f"/api/v1/recommendations/{rec_id}",
            params={"assessment_revision_id": str(revision_id)},
        )
    assert response.status_code == 404
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Cookie"
    assert observed == [(principal, rec_id, revision_id)]


@pytest.mark.parametrize("action", ["later", "not-relevant"])
def test_discovery_decisions_require_csrf_and_forward_exact_intent(action):
    from huginn.management.security.tokens import digest_token

    principal = Principal(uuid4(), uuid4())
    now = datetime.now(UTC)
    rec_id, revision_id = uuid4(), uuid4()
    observed = []

    class Commands:
        def later(self, actor, request):
            observed.append((actor, request))
            raise NotFoundError("Recommendation not found")

        mark_not_relevant = later

    keyword = "recommendation_decision_service"
    app = create_app(
        ManagementConfig("unused", environment="test"), **{keyword: Commands()}
    )
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    body = {
        "assessment_revision_id": str(revision_id),
        "request_key": "fixed-intent",
        "expected_recommendation_version": 3,
    }
    if action == "later":
        body.update(
            pause_choice="x2",
            expected_repeat_interval_days=45,
            expected_preference_updated_at=now.isoformat(),
            expected_pause_id=None,
            expected_pause_version=None,
        )
    with TestClient(app) as client:
        assert (
            client.post(
                f"/api/v1/recommendations/{rec_id}/{action}", json=body
            ).status_code
            == 403
        )
        response = client.post(
            f"/api/v1/recommendations/{rec_id}/{action}",
            json=body,
            headers={"X-CSRF-Token": "csrf"},
        )
        assert response.status_code == 404, response.text
        assert response.headers["vary"] == "Cookie"
        if action == "later":
            missing = {
                key: value for key, value in body.items() if key != "expected_pause_id"
            }
            assert (
                client.post(
                    f"/api/v1/recommendations/{rec_id}/{action}",
                    json=missing,
                    headers={"X-CSRF-Token": "csrf"},
                ).status_code
                == 422
            )
    assert len(observed) == 1
    assert observed[0][0] == principal
    assert observed[0][1].recommendation_id == rec_id
    assert observed[0][1].assessment_revision_id == revision_id
    if action == "later":
        assert observed[0][1].pause_choice.value == "x2"
        assert observed[0][1].expected_preference_updated_at == now


def test_generate_requires_csrf_and_returns_exact_stable_references():
    from huginn.management.application.read_models.generated_recommendation_reference import (
        GeneratedRecommendationReference,
    )
    from huginn.management.application.responses.generate_recommendations_response import (
        GenerateRecommendationsResponse,
    )
    from huginn.management.security.tokens import digest_token

    strategy_id, rec_id, revision_id, run_id = uuid4(), uuid4(), uuid4(), uuid4()
    principal = Principal(uuid4(), uuid4())
    observed = []

    class Generation:
        def execute(self, actor, request):
            observed.append((actor, request))
            return GenerateRecommendationsResponse(
                uuid4(),
                run_id,
                (GeneratedRecommendationReference(rec_id, revision_id, 3),),
            )

    app = create_app(
        ManagementConfig("unused", environment="test"),
        recommendation_generation_service=Generation(),
    )
    now = datetime.now(UTC)
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    with TestClient(app) as client:
        assert (
            client.post(
                "/api/v1/recommendations", json={"strategy_id": str(strategy_id)}
            ).status_code
            == 403
        )
        response = client.post(
            "/api/v1/recommendations",
            json={"strategy_id": str(strategy_id)},
            headers={"X-CSRF-Token": "csrf"},
        )
    assert response.status_code == 201, response.text
    assert response.json() == {
        "run_id": str(run_id),
        "references": [
            {
                "recommendation_id": str(rec_id),
                "revision_id": str(revision_id),
                "recommendation_version": 3,
            }
        ],
    }
    assert response.headers["cache-control"] == "no-store"
    assert observed[0][0] == principal
    assert observed[0][1].strategy_id == strategy_id
    assert observed[0][1].limit == 10


@pytest.mark.parametrize(
    ("action", "service_name", "extra"),
    [
        ("stage", "change_stage", {"target_stage": "contacted"}),
        ("close", "close", {"reason": "No longer active"}),
        ("reopen", "reopen", {}),
        ("notes", "update_notes", {"replacement_notes": "Canonical memo"}),
        (
            "follow-up",
            "set_follow_up",
            {"follow_up_at": "2026-12-01T12:00:00+00:00"},
        ),
        ("clear-follow-up", "clear_follow_up", {}),
        ("proposal-drafts", "record_proposal_draft", {"summary": "Draft only"}),
        (
            "activity-time-corrections",
            "correct_activity_time",
            {
                "original_activity_id": str(uuid4()),
                "expected_correction_head_id": None,
                "replacement_occurred_at": "2026-10-01T12:00:00+00:00",
            },
        ),
    ],
)
def test_pursuit_command_boundary_preserves_version_time_and_session_actor(
    action, service_name, extra
):
    from types import SimpleNamespace

    from huginn.management.security.tokens import digest_token

    principal = Principal(uuid4(), uuid4())
    prospect_id = uuid4()
    now = datetime.now(UTC)
    observed = []

    class Command:
        def execute(self, actor, request):
            observed.append((actor, request))
            raise NotFoundError("Prospect not found")

    app = create_app(
        ManagementConfig("unused", environment="test"),
        prospect_service=SimpleNamespace(**{service_name: Command().execute}),
    )
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    body = {"expected_version": 5, "request_key": "unchanged-intent", **extra}
    if action != "activity-time-corrections":
        body["occurred_at"] = now.isoformat()
    with TestClient(app) as client:
        assert (
            client.post(
                f"/api/v1/prospects/{prospect_id}/{action}", json=body
            ).status_code
            == 403
        )
        response = client.post(
            f"/api/v1/prospects/{prospect_id}/{action}",
            json=body,
            headers={"X-CSRF-Token": "csrf"},
        )
        assert response.status_code == 404, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["vary"] == "Cookie"
    assert observed[0][0] == principal
    assert observed[0][1].prospect_id == prospect_id
    assert observed[0][1].expected_version == 5
    if action == "stage":
        assert observed[0][1].target_stage.value == "contacted"
    if action != "activity-time-corrections":
        assert observed[0][1].occurred_at == now


@pytest.mark.parametrize("action", ["prepare", "confirm"])
def test_offer_commands_require_explicit_csrf_and_scope_cycle_from_session(action):
    from huginn.management.security.tokens import digest_token

    principal = Principal(uuid4(), uuid4())
    now = datetime.now(UTC)
    identity, revision_id = uuid4(), uuid4()
    observed = []

    class Command:
        def execute(self, actor, request):
            observed.append((actor, request))
            raise NotFoundError("Offer not found")

    name = (
        "prepare_recommendation_offer_service"
        if action == "prepare"
        else "confirm_recommendation_offer_service"
    )
    app = create_app(
        ManagementConfig("unused", environment="test"), **{name: Command()}
    )
    session = Session(
        uuid4(), principal.account_id, "digest", digest_token("csrf"), now, now, None
    )
    app.dependency_overrides[get_authenticated_session] = lambda: AuthenticatedSession(
        principal, session, "opaque"
    )
    path = (
        f"recommendations/{identity}/offer-preparations"
        if action == "prepare"
        else f"recommendations/offer-preparations/{identity}/confirm"
    )
    body = (
        {"assessment_revision_id": str(revision_id), "request_key": "same-intent"}
        if action == "prepare"
        else {"claim_token": "opaque-claim"}
    )
    with TestClient(app) as client:
        assert client.post(f"/api/v1/{path}", json=body).status_code == 403
        response = client.post(
            f"/api/v1/{path}", json=body, headers={"X-CSRF-Token": "csrf"}
        )
        assert response.status_code == 404, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["vary"] == "Cookie"
    assert len(observed) == 1
    assert observed[0][0] == principal
    if action == "prepare":
        assert observed[0][1].recommendation_id == identity
        assert observed[0][1].assessment_revision_id == revision_id
    else:
        assert observed[0][1].offer_cycle_id == identity
        assert observed[0][1].claim_token == "opaque-claim"
