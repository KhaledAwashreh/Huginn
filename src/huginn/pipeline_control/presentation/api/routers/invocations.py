"""Administrator admission and safe, paginated pipeline projections."""

from dataclasses import asdict
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, Response

from huginn.management.presentation.api.dependencies.administrator import Administrator
from huginn.management.presentation.api.dependencies.authentication import CsrfProtected
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.pipeline_control.application.requests.get_invocation_request import (
    GetInvocationRequest,
)
from huginn.pipeline_control.application.requests.list_events_request import (
    ListEventsRequest,
)
from huginn.pipeline_control.application.requests.list_invocation_companies_request import (
    ListInvocationCompaniesRequest,
)
from huginn.pipeline_control.application.requests.list_invocations_request import (
    ListInvocationsRequest,
)
from huginn.pipeline_control.application.requests.trigger_invocation_request import (
    TriggerInvocationRequest as TriggerCommand,
)
from huginn.pipeline_control.presentation.api.errors.active_invocation import (
    ActiveInvocationErrorResponse,
)
from huginn.pipeline_control.presentation.api.requests.list_events import (
    ListEventsQuery,
)
from huginn.pipeline_control.presentation.api.requests.list_invocation_companies import (
    ListInvocationCompaniesQuery,
)
from huginn.pipeline_control.presentation.api.requests.list_invocations import (
    ListInvocationsQuery,
)
from huginn.pipeline_control.presentation.api.requests.trigger_invocation import (
    TriggerInvocationRequest,
)
from huginn.pipeline_control.presentation.api.responses.event_page import (
    EventPageResponse,
)
from huginn.pipeline_control.presentation.api.responses.invocation_companies import (
    InvocationCompaniesResponse,
)
from huginn.pipeline_control.presentation.api.responses.invocation_detail import (
    InvocationDetailResponse,
)
from huginn.pipeline_control.presentation.api.responses.invocation_history import (
    InvocationHistoryResponse,
)
from huginn.pipeline_control.presentation.api.responses.invocation_receipt import (
    InvocationReceiptResponse,
)

router = APIRouter(
    prefix="/api/v1/admin/pipeline/invocations",
    tags=["Administrator pipeline"],
    responses=error_responses(401, 403, 404, 422),
)


def _lists(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_lists(item) for item in value]
    if isinstance(value, dict):
        return {key: _lists(item) for key, item in value.items()}
    return value


@router.post(
    "",
    status_code=202,
    response_model=InvocationReceiptResponse,
    responses={
        **error_responses(429),
        409: {
            "model": ActiveInvocationErrorResponse,
            "description": "Another invocation is active",
        },
    },
)
def trigger(
    body: TriggerInvocationRequest,
    administrator: Administrator,
    _csrf: CsrfProtected,
    dependencies: Management,
    response: Response,
) -> InvocationReceiptResponse:
    receipt = dependencies.pipeline_services.trigger.execute(
        TriggerCommand(administrator.principal.account_id, body.request_id)
    )
    response.headers["Location"] = f"{router.prefix}/{receipt.id}"
    return InvocationReceiptResponse(
        id=receipt.id, status=receipt.status, requested_at=receipt.requested_at
    )


@router.get("", response_model=InvocationHistoryResponse)
def history(
    query: Annotated[ListInvocationsQuery, Query()],
    _administrator: Administrator,
    dependencies: Management,
) -> InvocationHistoryResponse:
    result = dependencies.pipeline_services.history.execute(
        ListInvocationsRequest(query.limit, query.offset, query.state)
    )
    return InvocationHistoryResponse(
        items=list(result.items),
        limit=result.limit,
        offset=result.offset,
        has_more=result.has_more,
    )


@router.get("/{invocation_id}", response_model=InvocationDetailResponse)
def detail(
    invocation_id: UUID, _administrator: Administrator, dependencies: Management
) -> InvocationDetailResponse:
    result = dependencies.pipeline_services.get.execute(
        GetInvocationRequest(invocation_id)
    )
    return InvocationDetailResponse.model_validate(_lists(asdict(result.invocation)))


@router.get("/{invocation_id}/events", response_model=EventPageResponse)
def events(
    invocation_id: UUID,
    query: Annotated[ListEventsQuery, Query()],
    _administrator: Administrator,
    dependencies: Management,
) -> EventPageResponse:
    result = dependencies.pipeline_services.events.execute(
        ListEventsRequest(invocation_id, query.after_sequence, query.limit)
    )
    return EventPageResponse.model_validate(_lists(asdict(result)))


@router.get("/{invocation_id}/companies", response_model=InvocationCompaniesResponse)
def companies(
    invocation_id: UUID,
    query: Annotated[ListInvocationCompaniesQuery, Query()],
    _administrator: Administrator,
    dependencies: Management,
) -> InvocationCompaniesResponse:
    result = dependencies.pipeline_services.companies.execute(
        ListInvocationCompaniesRequest(invocation_id, query.limit, query.offset)
    )
    return InvocationCompaniesResponse.model_validate(_lists(asdict(result)))
