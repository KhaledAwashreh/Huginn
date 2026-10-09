"""Authoritative administrator admission and bounded operational projections."""

from dataclasses import asdict
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import JSONResponse

from huginn.management.presentation.api.dependencies.administrator import Administrator
from huginn.management.presentation.api.dependencies.authentication import CsrfProtected
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.responses.common import PageResponse
from huginn.matchmaking_control.application.requests.get_run_request import (
    GetRunRequest,
)
from huginn.matchmaking_control.application.requests.list_runs_request import (
    ListRunsRequest,
)
from huginn.matchmaking_control.application.requests.list_skipped_strategies_request import (
    ListSkippedStrategiesRequest,
)
from huginn.matchmaking_control.application.requests.list_target_users_request import (
    ListTargetUsersRequest,
)
from huginn.matchmaking_control.application.requests.list_user_results_request import (
    ListUserResultsRequest,
)
from huginn.matchmaking_control.application.requests.trigger_run_request import (
    TriggerRunRequest,
)
from huginn.matchmaking_control.domain.errors.run import (
    ActiveRunConflictError,
    NoEligibleUsersError,
    RequestIdentityConflictError,
    TargetUserDisabledError,
    TargetUserNotFoundError,
    TriggerRateLimitError,
)
from huginn.matchmaking_control.domain.value_objects.requester import Requester
from huginn.matchmaking_control.domain.value_objects.run_state import RunState
from huginn.matchmaking_control.domain.value_objects.target_state import TargetState
from huginn.matchmaking_control.presentation.api.requests.list_runs import ListRunsQuery
from huginn.matchmaking_control.presentation.api.requests.list_skipped_strategies import (
    ListSkippedStrategiesQuery,
)
from huginn.matchmaking_control.presentation.api.requests.list_target_users import (
    ListTargetUsersQuery,
)
from huginn.matchmaking_control.presentation.api.requests.list_user_results import (
    ListUserResultsQuery,
)
from huginn.matchmaking_control.presentation.api.requests.trigger_run import (
    TriggerRunBody,
)
from huginn.matchmaking_control.presentation.api.responses.run_detail import (
    RunDetailResponse,
)
from huginn.matchmaking_control.presentation.api.responses.run_receipt import (
    RunReceiptResponse,
)
from huginn.matchmaking_control.presentation.api.responses.run_summary import (
    RunSummaryResponse,
)
from huginn.matchmaking_control.presentation.api.responses.skipped_strategy_result import (
    SkippedStrategyResultResponse,
)
from huginn.matchmaking_control.presentation.api.responses.target_user_page import (
    TargetUserPageResponse,
)
from huginn.matchmaking_control.presentation.api.responses.user_result import (
    UserResultResponse,
)

router = APIRouter(
    prefix="/api/v1/admin/matchmaking",
    tags=["Administrator matchmaking"],
    responses=error_responses(401, 403, 404, 422),
)


def _page(page, model):
    if page is None:
        raise HTTPException(404)
    return {
        "items": [model.model_validate(asdict(item)) for item in page.items],
        "limit": page.limit,
        "offset": page.offset,
        "has_more": page.has_more,
    }


def _error(status, code, message, details=None):
    error = {"code": code, "message": message, "details": []}
    if details:
        error["details"] = [details]
    return JSONResponse(
        status_code=status,
        content={"error": error},
        headers={"Cache-Control": "no-store", "Vary": "Cookie"},
    )


@router.get("/users", response_model=TargetUserPageResponse)
def users(
    query: Annotated[ListTargetUsersQuery, Query()],
    _administrator: Administrator,
    dependencies: Management,
):
    result = dependencies.matchmaking_services.users.execute(
        ListTargetUsersRequest(query.search, query.offset, query.limit)
    )
    from huginn.matchmaking_control.presentation.api.responses.target_user import (
        TargetUserResponse,
    )

    return {
        **_page(result.page, TargetUserResponse),
        "total_eligible_count": result.total_eligible_count,
    }


@router.post(
    "/runs",
    status_code=202,
    response_model=RunReceiptResponse,
    responses=error_responses(409, 429),
)
def trigger(
    body: TriggerRunBody,
    administrator: Administrator,
    _csrf: CsrfProtected,
    dependencies: Management,
    response: Response,
):
    try:
        result = dependencies.matchmaking_services.trigger.execute(
            TriggerRunRequest(
                Requester(administrator.principal.account_id),
                body.request_id,
                body.target.kind,
                body.cutoff,
                body.as_of,
                getattr(body.target, "user_id", None),
            )
        )
    except ActiveRunConflictError as exc:
        return _error(
            409,
            "active_matching_run",
            "Another matching run is active",
            {"active_matching_run_id": str(exc.active_run_id)},
        )
    except RequestIdentityConflictError:
        return _error(
            409, "request_identity_conflict", "Request identity has different input"
        )
    except TargetUserNotFoundError:
        return _error(404, "not_found", "Target user was not found")
    except TargetUserDisabledError:
        return _error(422, "disabled_user", "Target user is disabled")
    except NoEligibleUsersError:
        return _error(422, "no_eligible_users", "No eligible users were found")
    except TriggerRateLimitError:
        response = _error(429, "rate_limited", "Too many matching requests")
        response.headers["Retry-After"] = "3600"
        return response
    except ValueError:
        return _error(422, "invalid_input", "Invalid matching window or target")
    response.headers["Location"] = f"{router.prefix}/runs/{result.id}"
    return RunReceiptResponse.model_validate(asdict(result))


@router.get("/runs", response_model=PageResponse[RunSummaryResponse])
def history(
    query: Annotated[ListRunsQuery, Query()],
    _administrator: Administrator,
    dependencies: Management,
):
    result = dependencies.matchmaking_services.history.execute(
        ListRunsRequest(
            query.limit, query.offset, RunState(query.state) if query.state else None
        )
    )
    return _page(result.page, RunSummaryResponse)


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def detail(run_id: UUID, _administrator: Administrator, dependencies: Management):
    result = dependencies.matchmaking_services.get.execute(GetRunRequest(run_id))
    if result.run is None:
        raise HTTPException(404)
    return RunDetailResponse.model_validate(asdict(result.run))


@router.get("/runs/{run_id}/users", response_model=PageResponse[UserResultResponse])
def results(
    run_id: UUID,
    query: Annotated[ListUserResultsQuery, Query()],
    _administrator: Administrator,
    dependencies: Management,
):
    result = dependencies.matchmaking_services.results.execute(
        ListUserResultsRequest(
            run_id,
            query.limit,
            query.offset,
            TargetState(query.state) if query.state else None,
        )
    )
    return _page(result.page, UserResultResponse)


@router.get(
    "/runs/{run_id}/users/{user_id}/skipped-strategies",
    response_model=PageResponse[SkippedStrategyResultResponse],
)
def skipped(
    run_id: UUID,
    user_id: UUID,
    query: Annotated[ListSkippedStrategiesQuery, Query()],
    _administrator: Administrator,
    dependencies: Management,
):
    result = dependencies.matchmaking_services.skipped.execute(
        ListSkippedStrategiesRequest(run_id, user_id, query.limit, query.offset)
    )
    return _page(result.page, SkippedStrategyResultResponse)
