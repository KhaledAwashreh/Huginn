"""Authenticated CRUD routes for ServiceOffering resources."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from huginn.management.dependencies.authentication import Authenticated, CsrfProtected
from huginn.management.dependencies.services import Management
from huginn.management.domain.service_offering import (
    NewServiceOffering,
    ServiceOffering,
    ServiceOfferingChanges,
)
from huginn.management.openapi_responses import error_responses
from huginn.management.requests.service_offering import (
    ServiceOfferingCreateRequest,
    ServiceOfferingUpdateRequest,
)
from huginn.management.responses.common import PageResponse
from huginn.management.responses.service_offering import ServiceOfferingResponse
from huginn.management.services.service_offerings import ServiceOfferingService

router = APIRouter(prefix="/api/v1/offerings", tags=["service offerings"])


def get_service_offering_service(
    dependencies: Management,
) -> ServiceOfferingService:
    """Provide the configured offering use case to this router."""
    return dependencies.service_offering_service


OfferingService = Annotated[
    ServiceOfferingService, Depends(get_service_offering_service)
]


def _response(offering: ServiceOffering) -> ServiceOfferingResponse:
    return ServiceOfferingResponse(
        id=offering.id,
        user_id=offering.user_id,
        name=offering.name,
        description=offering.description,
        created_at=offering.created_at,
        updated_at=offering.updated_at,
    )


@router.post(
    "",
    response_model=ServiceOfferingResponse,
    status_code=201,
    responses=error_responses(400, 401, 403, 409, 422),
)
def create_offering(
    body: ServiceOfferingCreateRequest,
    authenticated: CsrfProtected,
    service: OfferingService,
) -> ServiceOfferingResponse:
    offering = service.create(
        authenticated.principal,
        NewServiceOffering(
            user_id=authenticated.principal.user_id,
            name=body.name,
            description=body.description,
        ),
    )
    return _response(offering)


@router.get(
    "",
    response_model=PageResponse[ServiceOfferingResponse],
    responses=error_responses(401, 422),
)
def list_offerings(
    authenticated: Authenticated,
    service: OfferingService,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
) -> PageResponse[ServiceOfferingResponse]:
    page = service.list(authenticated.principal, limit=limit, offset=offset)
    return PageResponse(
        items=[_response(offering) for offering in page.items],
        offset=page.offset,
        limit=page.limit,
        has_more=page.has_more,
    )


@router.get(
    "/{offering_id}",
    response_model=ServiceOfferingResponse,
    responses=error_responses(401, 404, 422),
)
def get_offering(
    offering_id: UUID,
    authenticated: Authenticated,
    service: OfferingService,
) -> ServiceOfferingResponse:
    return _response(service.get(authenticated.principal, offering_id))


@router.patch(
    "/{offering_id}",
    response_model=ServiceOfferingResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def update_offering(
    offering_id: UUID,
    body: ServiceOfferingUpdateRequest,
    authenticated: CsrfProtected,
    service: OfferingService,
) -> ServiceOfferingResponse:
    offering = service.update(
        authenticated.principal,
        offering_id,
        ServiceOfferingChanges(
            values=body.model_dump(exclude_unset=True),
            supplied_fields=body.supplied_fields,
        ),
    )
    return _response(offering)


@router.delete(
    "/{offering_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 409, 422),
)
def delete_offering(
    offering_id: UUID,
    authenticated: CsrfProtected,
    service: OfferingService,
) -> Response:
    service.delete(authenticated.principal, offering_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
