from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.application.read_models.user_match import UserMatch
from huginn.management.application.requests.get_match_request import GetMatchRequest
from huginn.management.application.requests.get_matches_overview_request import (
    GetMatchesOverviewRequest,
)
from huginn.management.application.requests.list_match_signals_request import (
    ListMatchSignalsRequest,
)
from huginn.management.application.requests.list_matches_request import (
    ListMatchesRequest,
)
from huginn.management.application.services.get_match_service import GetMatchService
from huginn.management.application.services.get_matches_overview_service import (
    GetMatchesOverviewService,
)
from huginn.management.application.services.list_match_signals_service import (
    ListMatchSignalsService,
)
from huginn.management.application.services.list_matches_service import (
    ListMatchesService,
)
from huginn.management.domain.errors.errors import NotFoundError, ValidationDomainError
from huginn.management.domain.value_objects.common import Page, Principal
from huginn.management.domain.value_objects.match_status import MatchStatus


class UnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@dataclass
class Query:
    match: UserMatch | None
    overview: object

    def list_matches(self, user_id, status, offset, limit):
        self.list_arguments = (user_id, status, offset, limit)
        return Page(
            (self.match,) if self.match is not None else (), offset, limit, False
        )

    def get_match(self, user_id, match_id):
        self.get_arguments = (user_id, match_id)
        return self.match

    def list_match_signals(self, user_id, match_id, offset, limit):
        return Page((), offset, limit, False)

    def overview_for(self, user_id):
        self.overview_arguments = (user_id,)
        return self.overview


def _match(user_id):
    now = datetime.now(UTC)
    return UserMatch(
        id=uuid4(),
        user_id=user_id,
        status=MatchStatus("new"),
        notes=None,
        created_at=now,
        updated_at=now,
        company=CurrentCompany(
            id=uuid4(),
            name="Acme",
            domain="acme.test",
            business_sector=("AI",),
            country="US",
            company_scale="0-10",
            company_status="Active",
        ),
    )


def test_get_match_is_owner_scoped_and_maps_missing_to_not_found():
    principal = Principal(uuid4(), uuid4())
    match = _match(principal.user_id)
    query = Query(match, None)
    service = GetMatchService(lambda: UnitOfWork(), query_factory=lambda _: query)

    result = service.execute(GetMatchRequest(principal, match.id))

    assert result.match is match
    assert query.get_arguments == (principal.user_id, match.id)
    query.match = None
    with pytest.raises(NotFoundError):
        service.execute(GetMatchRequest(principal, match.id))


def test_list_matches_rejects_unrepresentable_offset_and_bounds_page():
    principal = Principal(uuid4(), uuid4())
    match = _match(principal.user_id)
    query = Query(match, None)
    service = ListMatchesService(lambda: UnitOfWork(), query_factory=lambda _: query)

    response = service.execute(
        ListMatchesRequest(principal, status=MatchStatus("new"), limit=100, offset=12)
    )

    assert response.page.items == (match,)
    assert query.list_arguments == (principal.user_id, MatchStatus("new"), 12, 100)
    for limit, offset in (
        (0, 0),
        (101, 0),
        (50, -1),
        (50, 9_223_372_036_854_775_808),
        (True, 0),
    ):
        with pytest.raises(ValidationDomainError):
            ListMatchesRequest(principal, limit=limit, offset=offset)
        with pytest.raises(ValidationDomainError):
            ListMatchSignalsRequest(principal, match.id, limit=limit, offset=offset)


def test_signal_page_requires_an_owned_match_before_querying_signals():
    principal = Principal(uuid4(), uuid4())
    match = _match(principal.user_id)
    query = Query(match, None)
    service = ListMatchSignalsService(
        lambda: UnitOfWork(), query_factory=lambda _: query
    )

    assert (
        service.execute(ListMatchSignalsRequest(principal, match.id)).page.items == ()
    )
    query.match = None
    with pytest.raises(NotFoundError):
        service.execute(ListMatchSignalsRequest(principal, match.id))


def test_overview_query_receives_authenticated_owner():
    principal = Principal(uuid4(), uuid4())
    query = Query(None, object())
    service = GetMatchesOverviewService(
        lambda: UnitOfWork(), query_factory=lambda _: query
    )

    service.execute(GetMatchesOverviewRequest(principal))

    assert query.overview_arguments == (principal.user_id,)
