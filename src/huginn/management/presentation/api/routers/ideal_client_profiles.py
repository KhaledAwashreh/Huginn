"""Owner-scoped IdealClientProfile endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from huginn.management.application.services.ideal_client_profiles import (
    IdealClientProfileService,
)
from huginn.management.domain.value_objects.ideal_client_profile import (
    IdealClientProfileChanges,
    NewIdealClientProfile,
)
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    CsrfProtected,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.mapping import (
    request_to_changes,
    request_to_domain,
    response_from_domain,
)
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.requests.ideal_client_profile import (
    IdealClientProfileCreateRequest,
    IdealClientProfileUpdateRequest,
)
from huginn.management.presentation.api.responses.common import PageResponse
from huginn.management.presentation.api.responses.ideal_client_profile import (
    IdealClientProfileResponse,
)

router = APIRouter(
    prefix="/api/v1/ideal-client-profiles", tags=["ideal-client-profiles"]
)


def get_ideal_client_profile_service(
    dependencies: Management,
) -> IdealClientProfileService:
    return dependencies.ideal_client_profile_service


IdealClientProfiles = Annotated[
    IdealClientProfileService, Depends(get_ideal_client_profile_service)
]


@router.post(
    "",
    response_model=IdealClientProfileResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 401, 403, 409, 422),
)
def create_ideal_client_profile(
    body: IdealClientProfileCreateRequest,
    authenticated: CsrfProtected,
    service: IdealClientProfiles,
) -> IdealClientProfileResponse:
    created = service.create(
        authenticated.principal,
        request_to_domain(
            body,
            NewIdealClientProfile,
            user_id=authenticated.principal.user_id,
        ),
    )
    return response_from_domain(created, IdealClientProfileResponse)


@router.get(
    "",
    response_model=PageResponse[IdealClientProfileResponse],
    responses=error_responses(401, 422),
)
def list_ideal_client_profiles(
    authenticated: Authenticated,
    service: IdealClientProfiles,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
) -> PageResponse[IdealClientProfileResponse]:
    page = service.list(authenticated.principal, limit=limit, offset=offset)
    return PageResponse[IdealClientProfileResponse](
        items=[
            response_from_domain(item, IdealClientProfileResponse)
            for item in page.items
        ],
        offset=page.offset,
        limit=page.limit,
        has_more=page.has_more,
    )


@router.get(
    "/{profile_id}",
    response_model=IdealClientProfileResponse,
    responses=error_responses(401, 404, 422),
)
def get_ideal_client_profile(
    profile_id: UUID,
    authenticated: Authenticated,
    service: IdealClientProfiles,
) -> IdealClientProfileResponse:
    value = service.get(authenticated.principal, profile_id)
    return response_from_domain(value, IdealClientProfileResponse)


@router.patch(
    "/{profile_id}",
    response_model=IdealClientProfileResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def update_ideal_client_profile(
    profile_id: UUID,
    body: IdealClientProfileUpdateRequest,
    authenticated: CsrfProtected,
    service: IdealClientProfiles,
) -> IdealClientProfileResponse:
    value = service.update(
        authenticated.principal,
        profile_id,
        request_to_changes(body, IdealClientProfileChanges),
    )
    return response_from_domain(value, IdealClientProfileResponse)


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422),
)
def delete_ideal_client_profile(
    profile_id: UUID,
    authenticated: CsrfProtected,
    service: IdealClientProfiles,
) -> Response:
    service.delete(authenticated.principal, profile_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
