"""Authenticated read-only endpoints for the current user's Matches."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Response

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
from huginn.management.domain.value_objects.match_status import MatchStatus
from huginn.management.presentation.api.dependencies.authentication import Authenticated
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.requests.matches import MatchStatusFilter
from huginn.management.presentation.api.responses.common import PageResponse
from huginn.management.presentation.api.responses.current_company import (
    CurrentCompanyResponse,
)
from huginn.management.presentation.api.responses.current_company_signal import (
    CurrentCompanySignalResponse,
)
from huginn.management.presentation.api.responses.evaluation_summary import (
    EvaluationSummaryResponse,
)
from huginn.management.presentation.api.responses.matches_overview import (
    MatchesOverviewResponse,
)
from huginn.management.presentation.api.responses.user_match import UserMatchResponse

router = APIRouter(prefix="/api/v1/matches", tags=["matches"])


def _private(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


def _match_response(item) -> UserMatchResponse:
    company = item.company
    return UserMatchResponse(
        id=item.id,
        status=item.status.value,
        notes=item.notes,
        created_at=item.created_at,
        updated_at=item.updated_at,
        company=CurrentCompanyResponse(
            name=company.name,
            domain=company.domain,
            business_sector=None
            if company.business_sector is None
            else list(company.business_sector),
            country=company.country,
            company_scale=company.company_scale,
            company_status=company.company_status,
        ),
    )


@router.get(
    "/overview", response_model=MatchesOverviewResponse, responses=error_responses(401)
)
def get_matches_overview(
    authenticated: Authenticated, response: Response, dependencies: Management
) -> MatchesOverviewResponse:
    overview = dependencies.get_matches_overview_service.execute(
        GetMatchesOverviewRequest(authenticated.principal)
    ).overview
    latest = overview.latest_evaluation
    result = MatchesOverviewResponse(
        has_matches=overview.has_matches,
        has_active_strategies=overview.has_active_strategies,
        latest_evaluation=None
        if latest is None
        else EvaluationSummaryResponse(
            **{
                "state": latest.state,
                "requested_at": latest.requested_at,
                "started_at": latest.started_at,
                "finished_at": latest.finished_at,
                "cutoff": latest.cutoff,
                "as_of": latest.as_of,
                "tracking_stale": latest.tracking_stale,
                "strategies_evaluated": latest.strategies_evaluated,
                "strategies_skipped": latest.strategies_skipped,
                "created_matches_count": latest.created_matches_count,
                "existing_matches_skipped_count": latest.existing_matches_skipped_count,
            }
        ),
    )
    _private(response)
    return result


@router.get(
    "",
    response_model=PageResponse[UserMatchResponse],
    responses=error_responses(401, 422),
)
def list_matches(
    authenticated: Authenticated,
    response: Response,
    dependencies: Management,
    status: MatchStatusFilter | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
) -> PageResponse[UserMatchResponse]:
    page = dependencies.list_matches_service.execute(
        ListMatchesRequest(
            authenticated.principal,
            None if status is None else MatchStatus(status),
            limit,
            offset,
        )
    ).page
    _private(response)
    return PageResponse(
        items=[_match_response(item) for item in page.items],
        offset=page.offset,
        limit=page.limit,
        has_more=page.has_more,
    )


@router.get(
    "/{match_id}/signals",
    response_model=PageResponse[CurrentCompanySignalResponse],
    responses=error_responses(401, 404, 422),
)
def list_match_signals(
    match_id: UUID,
    authenticated: Authenticated,
    response: Response,
    dependencies: Management,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
) -> PageResponse[CurrentCompanySignalResponse]:
    page = dependencies.list_match_signals_service.execute(
        ListMatchSignalsRequest(authenticated.principal, match_id, limit, offset)
    ).page
    _private(response)
    return PageResponse(
        items=[
            CurrentCompanySignalResponse(
                id=item.id,
                signal_type=item.signal_type,
                source=item.source,
                source_url=item.source_url,
                description=item.description,
                stage=item.stage,
                occurred_at=item.occurred_at,
                ingested_at=item.ingested_at,
            )
            for item in page.items
        ],
        offset=page.offset,
        limit=page.limit,
        has_more=page.has_more,
    )


@router.get(
    "/{match_id}",
    response_model=UserMatchResponse,
    responses=error_responses(401, 404, 422),
)
def get_match(
    match_id: UUID,
    authenticated: Authenticated,
    response: Response,
    dependencies: Management,
) -> UserMatchResponse:
    match = dependencies.get_match_service.execute(
        GetMatchRequest(authenticated.principal, match_id)
    ).match
    _private(response)
    return _match_response(match)
