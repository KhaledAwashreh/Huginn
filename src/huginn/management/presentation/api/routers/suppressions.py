"""Manage hidden Companies without creating a relationship or assessment."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from huginn.management.application.requests.cancel_recommendation_pause_request import (
    CancelRecommendationPauseRequest,
)
from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)
from huginn.management.application.requests.reverse_recommendation_rejection_request import (
    ReverseRecommendationRejectionRequest,
)
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    CsrfProtected,
)
from huginn.management.presentation.api.dependencies.prospecting import (
    private_prospecting_response,
    prospecting_page,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.mapping import response_from_domain
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.prospecting_mapping import suppression_response
from huginn.management.presentation.api.requests.clear_recommendation_suppression import (
    ClearRecommendationSuppressionRequest,
)
from huginn.management.presentation.api.responses.clear_recommendation_suppression import (
    ClearRecommendationSuppressionResponse,
)
from huginn.management.presentation.api.responses.common import PageResponse
from huginn.management.presentation.api.responses.prospecting_suppression import (
    SuppressionResponse,
)

router = APIRouter(
    prefix="/api/v1/suppressions",
    tags=["suppressions"],
    dependencies=[Depends(private_prospecting_response)],
)


@router.get(
    "",
    response_model=PageResponse[SuppressionResponse],
    responses=error_responses(401, 404, 422),
)
def list_suppressions(
    authenticated: Authenticated,
    dependencies: Management,
    page: Annotated[ListProspectingRequest, Depends(prospecting_page)],
):
    result = dependencies.prospecting_read_service.list_manageable_suppressions(
        authenticated.principal, page
    )
    return PageResponse[SuppressionResponse](
        items=[suppression_response(item) for item in result.items],
        offset=result.offset,
        limit=result.limit,
        has_more=result.has_more,
    )


@router.post(
    "/{suppression_block_id}/reverse-rejection",
    response_model=ClearRecommendationSuppressionResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def reverse_rejection(
    suppression_block_id: UUID,
    body: ClearRecommendationSuppressionRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    command = ReverseRecommendationRejectionRequest(
        suppression_block_id, body.expected_version, body.request_key
    )
    return response_from_domain(
        dependencies.recommendation_decision_service.reverse_rejection(
            authenticated.principal, command
        ),
        ClearRecommendationSuppressionResponse,
    )


@router.post(
    "/{suppression_block_id}/cancel-pause",
    response_model=ClearRecommendationSuppressionResponse,
    responses=error_responses(401, 403, 404, 409, 422),
)
def cancel_pause(
    suppression_block_id: UUID,
    body: ClearRecommendationSuppressionRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
):
    command = CancelRecommendationPauseRequest(
        suppression_block_id, body.expected_version, body.request_key
    )
    return response_from_domain(
        dependencies.recommendation_decision_service.cancel_pause(
            authenticated.principal, command
        ),
        ClearRecommendationSuppressionResponse,
    )
