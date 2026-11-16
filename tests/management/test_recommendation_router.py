from uuid import uuid4

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.errors.errors import NotFoundError
from tests.management.test_matches_read_router import SESSION_TOKEN, FakeAuthentication


class Service:
    def __init__(self):
        self.calls = []

    def execute(self, principal, request):
        from huginn.management.application.responses.generate_recommendations_response import (
            GenerateRecommendationsResponse,
        )

        self.calls.append((principal.user_id, request.strategy_id, request.limit))
        return GenerateRecommendationsResponse(uuid4(), uuid4(), ())

    def get_recommendation(self, *args, **kwargs):
        raise NotFoundError("Recommendation not found")

    def list_recommendations(self, principal, request, *, status):
        from huginn.management.domain.value_objects.common import Page

        self.calls.append((principal.user_id, request.limit, request.offset))
        return Page((), request.offset, request.limit, False)


def test_shared_collection_is_owner_scoped_read_only_and_private():
    owner = uuid4()
    service = Service()
    app = create_app(
        ManagementConfig("unused", environment="test"),
        authentication_service=FakeAuthentication(owner),
        recommendation_generation_service=service,
        prospecting_read_service=service,
    )
    with TestClient(app) as client:
        url = "/api/v1/recommendations"
        assert client.get(url).status_code == 401
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        response = client.get(url, params={"limit": 2, "offset": 3})
        assert response.status_code == 200 and response.json()["items"] == []
        assert response.headers["cache-control"] == "no-store"
        assert service.calls[-1] == (owner, 2, 3)
        assert client.get(url, params={"offset": 2**63 - 1}).status_code == 200
        assert client.get(url, params={"offset": 2**63}).status_code == 422
        assert client.put(url, headers={"X-CSRF-Token": "csrf"}).status_code == 405


def test_recommendation_mutation_requires_session_csrf_and_owner_identity():
    owner = uuid4()
    service = Service()
    app = create_app(
        ManagementConfig("unused", environment="test"),
        authentication_service=FakeAuthentication(owner),
        recommendation_generation_service=service,
        prospecting_read_service=service,
    )
    with TestClient(app) as client:
        strategy = uuid4()
        url = "/api/v1/recommendations"
        assert client.post(url, json={"strategy_id": str(strategy)}).status_code == 401
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        assert client.post(url, json={"strategy_id": str(strategy)}).status_code == 403
        response = client.post(
            url, json={"strategy_id": str(strategy)}, headers={"X-CSRF-Token": "csrf"}
        )
        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        assert service.calls[-1] == (owner, strategy, 10)
        assert client.get(url + "/" + str(uuid4())).status_code == 404
        invalid = client.post(
            url,
            json={"strategy_id": str(strategy), "limit": True},
            headers={"X-CSRF-Token": "csrf"},
        )
        assert invalid.status_code == 422
        assert invalid.headers["cache-control"] == "no-store"


class MissingFeedback:
    def execute(self, *args):
        raise NotFoundError("Recommendation not found")


def test_feedback_body_is_strict_and_private():
    app = create_app(
        ManagementConfig("unused", environment="test"),
        authentication_service=FakeAuthentication(uuid4()),
        record_recommendation_feedback_service=MissingFeedback(),
    )
    with TestClient(app) as client:
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        url = f"/api/v1/recommendations/{uuid4()}/feedback"
        base = {
            "assessment_revision_id": str(uuid4()),
            "request_key": "feedback",
            "feedback": {"usefulness": "unsure"},
        }
        assert client.post(url, json=base).status_code == 403
        invalid = client.post(
            url,
            json={
                **base,
                "feedback": {"usefulness": "unsure", "reasons": ["invented"]},
            },
            headers={"X-CSRF-Token": "csrf"},
        )
        assert invalid.status_code == 422
        response = client.post(url, json=base, headers={"X-CSRF-Token": "csrf"})
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"


def test_generation_throttle_returns_private_retry_after_response():
    from huginn.management.application.errors.errors import RateLimitError

    class LimitedService(Service):
        def execute(self, principal, request):
            raise RateLimitError("Recommendation generation limit reached", 42)

    app = create_app(
        ManagementConfig("unused", environment="test"),
        authentication_service=FakeAuthentication(uuid4()),
        recommendation_generation_service=LimitedService(),
    )
    with TestClient(app) as client:
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        response = client.post(
            "/api/v1/recommendations",
            json={"strategy_id": str(uuid4())},
            headers={"X-CSRF-Token": "csrf"},
        )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "42"
    assert response.headers["cache-control"] == "no-store"
