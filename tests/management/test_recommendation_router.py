from uuid import uuid4

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.domain.errors.errors import NotFoundError
from tests.management.test_matches_read_router import SESSION_TOKEN, FakeAuthentication


class Service:
    calls = []

    def generate(self, user, strategy, limit):
        self.calls.append((user, strategy, limit))
        return {
            "id": str(uuid4()),
            "strategy_id": str(strategy),
            "created_at": "2026-10-28T12:00:00Z",
            "algorithm_version": "research-ranking-v1",
            "assessment_method": "topic-overlap-v1",
            "candidate_count": 0,
            "retrieval_limit": 200,
            "items": [],
        }

    def get(self, *args):
        raise NotFoundError("Recommendation batch not found")

    def latest(self, *args):
        raise NotFoundError("Recommendation batch not found")

    def feedback(self, *args):
        raise NotFoundError("Recommendation batch not found")

    def review(self, *args):
        raise NotFoundError("Recommendation not found")


def test_recommendation_mutation_requires_session_csrf_and_owner_identity():
    owner = uuid4()
    service = Service()
    app = create_app(
        ManagementConfig("unused", environment="test"),
        authentication_service=FakeAuthentication(owner),
        recommendation_service=service,
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
        assert (
            client.get(
                url + "/latest", params={"strategy_id": str(strategy)}
            ).status_code
            == 404
        )
        assert client.get(url + "/" + str(uuid4())).status_code == 404
        invalid = client.post(
            url,
            json={"strategy_id": str(strategy), "limit": True},
            headers={"X-CSRF-Token": "csrf"},
        )
        assert invalid.status_code == 422
        assert invalid.headers["cache-control"] == "no-store"


def test_feedback_body_is_strict_and_private():
    app = create_app(
        ManagementConfig("unused", environment="test"),
        authentication_service=FakeAuthentication(uuid4()),
        recommendation_service=Service(),
    )
    with TestClient(app) as client:
        client.cookies.set("huginn_management_session", SESSION_TOKEN)
        url = f"/api/v1/recommendations/{uuid4()}/feedback"
        base = {"recommendation_id": "a" * 64, "usefulness": "unsure"}
        assert client.post(url, json=base).status_code == 403
        invalid = client.post(
            url,
            json={**base, "reasons": ["invented"]},
            headers={"X-CSRF-Token": "csrf"},
        )
        assert invalid.status_code == 422
        response = client.post(url, json=base, headers={"X-CSRF-Token": "csrf"})
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
