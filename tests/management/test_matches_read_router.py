from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.application.read_models.current_company_signal import (
    CurrentCompanySignal,
)
from huginn.management.application.read_models.matches_overview import MatchesOverview
from huginn.management.application.read_models.user_match import UserMatch
from huginn.management.application.responses.get_match_response import GetMatchResponse
from huginn.management.application.responses.get_matches_overview_response import (
    GetMatchesOverviewResponse,
)
from huginn.management.application.responses.list_match_signals_response import (
    ListMatchSignalsResponse,
)
from huginn.management.application.responses.list_matches_response import (
    ListMatchesResponse,
)
from huginn.management.application.services.authentication import AuthenticatedSession
from huginn.management.config import ManagementConfig
from huginn.management.domain.entities.session import Session
from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import Page, Principal
from huginn.management.domain.value_objects.match_status import MatchStatus

SESSION_TOKEN = "matches-test-session"


class UseCase:
    def __init__(self, function):
        self._function = function

    def execute(self, request):
        return self._function(request)


class FakeAuthentication:
    def __init__(self, user_id: UUID):
        self.principal = Principal(uuid4(), user_id)
        now = datetime.now(UTC)
        self.session = Session(
            uuid4(),
            self.principal.account_id,
            sha256(SESSION_TOKEN.encode()).hexdigest(),
            sha256(b"csrf").hexdigest(),
            now,
            now + timedelta(hours=1),
            None,
        )

    def authenticate_session(self, token: str):
        return (
            AuthenticatedSession(self.principal, self.session)
            if token == SESSION_TOKEN
            else None
        )


@dataclass
class FakeMatchesServices:
    owner_id: UUID

    def __post_init__(self):
        now = datetime.now(UTC)
        self.match = UserMatch(
            uuid4(),
            self.owner_id,
            MatchStatus("new"),
            None,
            now,
            now,
            CurrentCompany(
                uuid4(), "Acme", "acme.test", ("AI",), "US", "0-10", "Active"
            ),
        )
        self.calls = []

    def list_matches(self, request):
        self.calls.append(("list", request))
        return ListMatchesResponse(
            Page((self.match,), request.offset, request.limit, False)
        )

    def get_match(self, request):
        self.calls.append(("detail", request))
        if (
            request.match_id != self.match.id
            or request.principal.user_id != self.owner_id
        ):
            raise NotFoundError("Match not found")
        return GetMatchResponse(self.match)

    def list_match_signals(self, request):
        self.calls.append(("signals", request))
        if (
            request.match_id != self.match.id
            or request.principal.user_id != self.owner_id
        ):
            raise NotFoundError("Match not found")
        now = self.match.created_at
        signal = CurrentCompanySignal(
            uuid4(), "hiring", "hn", "https://example.test", "Hiring", "seed", now, now
        )
        return ListMatchSignalsResponse(
            Page((signal,), request.offset, request.limit, False)
        )

    def get_matches_overview(self, request):
        self.calls.append(("overview", request))
        return GetMatchesOverviewResponse(MatchesOverview(True, True, None))


def _client(owner_id: UUID, services: FakeMatchesServices) -> TestClient:
    app = create_app(
        ManagementConfig("unused", environment="test"),
        authentication_service=FakeAuthentication(owner_id),
        list_matches_service=UseCase(services.list_matches),
        get_match_service=UseCase(services.get_match),
        list_match_signals_service=UseCase(services.list_match_signals),
        get_matches_overview_service=UseCase(services.get_matches_overview),
    )
    client = TestClient(app)
    client.cookies.set("huginn_management_session", SESSION_TOKEN)
    return client


def _private(response):
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["vary"] == "Cookie"


def test_authenticated_matches_routes_map_current_context_and_bound_pages():
    owner_id = uuid4()
    services = FakeMatchesServices(owner_id)
    with _client(owner_id, services) as client:
        listed = client.get("/api/v1/matches?status=new&limit=100&offset=4")
        assert listed.status_code == 200
        _private(listed)
        body = listed.json()
        assert body["items"][0]["company"] == {
            "name": "Acme",
            "domain": "acme.test",
            "business_sector": ["AI"],
            "country": "US",
            "company_scale": "0-10",
            "company_status": "Active",
        }
        assert body["offset"] == 4 and body["limit"] == 100
        assert services.calls[-1][1].principal.user_id == owner_id

        detail = client.get(f"/api/v1/matches/{services.match.id}")
        overview = client.get("/api/v1/matches/overview")
        signals = client.get(f"/api/v1/matches/{services.match.id}/signals?limit=2")
        for response in (detail, overview, signals):
            assert response.status_code == 200
            _private(response)
        assert detail.json()["id"] == str(services.match.id)
        assert overview.json() == {
            "has_matches": True,
            "has_active_strategies": True,
            "latest_evaluation": None,
        }
        assert signals.json()["items"][0]["signal_type"] == "hiring"

        invalid_status = client.get("/api/v1/matches?status=bogus")
        invalid_page = client.get("/api/v1/matches?limit=101")
        oversized_offset = client.get("/api/v1/matches?offset=9223372036854775808")
        for response in (invalid_status, invalid_page, oversized_offset):
            assert response.status_code == 422
            _private(response)


def test_owner_and_missing_match_ids_share_private_not_found_and_no_company_endpoint():
    owner_id = uuid4()
    services = FakeMatchesServices(owner_id)
    with _client(uuid4(), services) as client:
        other = client.get(f"/api/v1/matches/{services.match.id}")
        missing = client.get(f"/api/v1/matches/{uuid4()}")
        assert other.status_code == missing.status_code == 404
        assert other.json() == missing.json()
        _private(other)
        _private(missing)
        no_company_api = client.get(f"/api/v1/matches/companies/{uuid4()}/signals")
        assert no_company_api.status_code == 404
        _private(no_company_api)


def test_matches_authentication_errors_are_private():
    services = FakeMatchesServices(uuid4())
    with _client(services.owner_id, services) as client:
        client.cookies.clear()
        response = client.get("/api/v1/matches")
        assert response.status_code == 401
        _private(response)
