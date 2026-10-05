"""Owner-scoped ClientDiscoveryStrategy endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status

from huginn.management.application.services.discovery_strategies import (
    ClientDiscoveryStrategyService,
)
from huginn.management.domain.value_objects.client_discovery_strategy import (
    ClientDiscoveryStrategyChanges,
    NewClientDiscoveryStrategy,
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
from huginn.management.presentation.api.requests.discovery_strategy import (
    DiscoveryStrategyCreateRequest,
    DiscoveryStrategyUpdateRequest,
)
from huginn.management.presentation.api.responses.common import PageResponse
from huginn.management.presentation.api.responses.discovery_strategy import (
    DiscoveryStrategyResponse,
)

router = APIRouter(prefix="/api/v1/discovery-strategies", tags=["discovery-strategies"])


def get_discovery_strategy_service(
    dependencies: Management,
) -> ClientDiscoveryStrategyService:
    return dependencies.discovery_strategy_service


DiscoveryStrategies = Annotated[
    ClientDiscoveryStrategyService, Depends(get_discovery_strategy_service)
]


@router.post(
    "",
    response_model=DiscoveryStrategyResponse,
    status_code=status.HTTP_201_CREATED,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def create_discovery_strategy(
    body: DiscoveryStrategyCreateRequest,
    authenticated: CsrfProtected,
    service: DiscoveryStrategies,
) -> DiscoveryStrategyResponse:
    value = service.create(
        authenticated.principal,
        request_to_domain(
            body,
            NewClientDiscoveryStrategy,
            user_id=authenticated.principal.user_id,
        ),
    )
    return response_from_domain(value, DiscoveryStrategyResponse)


@router.get(
    "",
    response_model=PageResponse[DiscoveryStrategyResponse],
    responses=error_responses(401, 422),
)
def list_discovery_strategies(
    authenticated: Authenticated,
    service: DiscoveryStrategies,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=9_223_372_036_854_775_807)] = 0,
    active: bool | None = None,
) -> PageResponse[DiscoveryStrategyResponse]:
    page = service.list(
        authenticated.principal, limit=limit, offset=offset, active=active
    )
    return PageResponse[DiscoveryStrategyResponse](
        items=[
            response_from_domain(item, DiscoveryStrategyResponse) for item in page.items
        ],
        offset=page.offset,
        limit=page.limit,
        has_more=page.has_more,
    )


@router.get(
    "/{strategy_id}",
    response_model=DiscoveryStrategyResponse,
    responses=error_responses(401, 404, 422),
)
def get_discovery_strategy(
    strategy_id: UUID,
    authenticated: Authenticated,
    service: DiscoveryStrategies,
) -> DiscoveryStrategyResponse:
    value = service.get(authenticated.principal, strategy_id)
    return response_from_domain(value, DiscoveryStrategyResponse)


@router.patch(
    "/{strategy_id}",
    response_model=DiscoveryStrategyResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def update_discovery_strategy(
    strategy_id: UUID,
    body: DiscoveryStrategyUpdateRequest,
    authenticated: CsrfProtected,
    service: DiscoveryStrategies,
) -> DiscoveryStrategyResponse:
    value = service.update(
        authenticated.principal,
        strategy_id,
        request_to_changes(body, ClientDiscoveryStrategyChanges),
    )
    return response_from_domain(value, DiscoveryStrategyResponse)


@router.delete(
    "/{strategy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=error_responses(401, 403, 404, 422),
)
def delete_discovery_strategy(
    strategy_id: UUID,
    authenticated: CsrfProtected,
    service: DiscoveryStrategies,
) -> Response:
    service.delete(authenticated.principal, strategy_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
