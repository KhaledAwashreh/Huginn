"""Authenticated Business profile and recommendation preference endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from huginn.management.application.services.business_profile import (
    BusinessProfileService,
)
from huginn.management.application.services.business_recommendation_preferences import (
    BusinessRecommendationPreferencesService,
)
from huginn.management.application.services.business_setup import BusinessSetupService
from huginn.management.domain.value_objects.business_changes import BusinessChanges
from huginn.management.domain.value_objects.business_recommendation_preferences import (
    BusinessRecommendationPreferencesChanges,
)
from huginn.management.domain.value_objects.ideal_client_profile import (
    IdealClientProfileChanges,
)
from huginn.management.presentation.api.dependencies.authentication import (
    Authenticated,
    CsrfProtected,
)
from huginn.management.presentation.api.dependencies.services import Management
from huginn.management.presentation.api.mapping import (
    request_to_changes,
    response_from_domain,
)
from huginn.management.presentation.api.openapi.responses import error_responses
from huginn.management.presentation.api.requests.business_profile import (
    BusinessProfileUpdateRequest,
)
from huginn.management.presentation.api.requests.business_recommendation_preferences import (
    BusinessRecommendationPreferencesUpdateRequest,
)
from huginn.management.presentation.api.requests.business_setup import (
    BusinessSetupUpdateRequest,
)
from huginn.management.presentation.api.responses.business_profile import (
    BusinessProfileResponse,
)
from huginn.management.presentation.api.responses.business_recommendation_preferences import (
    BusinessRecommendationPreferencesResponse,
)
from huginn.management.presentation.api.responses.business_setup import (
    BusinessSetupResponse,
)

router = APIRouter(prefix="/api/v1/me", tags=["current-business"])


def get_business_profile_service(dependencies: Management) -> BusinessProfileService:
    return dependencies.business_profile_service


def get_business_recommendation_preferences_service(
    dependencies: Management,
) -> BusinessRecommendationPreferencesService:
    return dependencies.business_recommendation_preferences_service


BusinessProfile = Annotated[
    BusinessProfileService, Depends(get_business_profile_service)
]
BusinessPreferences = Annotated[
    BusinessRecommendationPreferencesService,
    Depends(get_business_recommendation_preferences_service),
]


@router.get(
    "/business",
    response_model=BusinessProfileResponse,
    responses=error_responses(401, 404),
)
def get_business_profile(
    authenticated: Authenticated, service: BusinessProfile
) -> BusinessProfileResponse:
    return response_from_domain(
        service.get(authenticated.principal), BusinessProfileResponse
    )


@router.patch(
    "/business",
    response_model=BusinessProfileResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def update_business_profile(
    body: BusinessProfileUpdateRequest,
    authenticated: CsrfProtected,
    service: BusinessProfile,
) -> BusinessProfileResponse:
    changes = request_to_changes(body, BusinessChanges)
    return response_from_domain(
        service.update(authenticated.principal, changes), BusinessProfileResponse
    )


@router.get(
    "/business/recommendation-preferences",
    response_model=BusinessRecommendationPreferencesResponse,
    responses=error_responses(401, 404),
)
def get_business_recommendation_preferences(
    authenticated: Authenticated, service: BusinessPreferences
) -> BusinessRecommendationPreferencesResponse:
    return response_from_domain(
        service.get(authenticated.principal),
        BusinessRecommendationPreferencesResponse,
    )


@router.patch(
    "/business/recommendation-preferences",
    response_model=BusinessRecommendationPreferencesResponse,
    responses=error_responses(400, 401, 403, 404, 422),
)
def update_business_recommendation_preferences(
    body: BusinessRecommendationPreferencesUpdateRequest,
    authenticated: CsrfProtected,
    service: BusinessPreferences,
) -> BusinessRecommendationPreferencesResponse:
    changes = BusinessRecommendationPreferencesChanges(
        repeat_interval_days=body.repeat_interval_days
    )
    return response_from_domain(
        service.update(authenticated.principal, changes),
        BusinessRecommendationPreferencesResponse,
    )


@router.get(
    "/business/setup",
    response_model=BusinessSetupResponse,
    responses=error_responses(401, 404, 409),
)
def get_business_setup(
    authenticated: Authenticated, dependencies: Management
) -> BusinessSetupResponse:
    return response_from_domain(
        dependencies.business_setup_service.get(authenticated.principal),
        BusinessSetupResponse,
    )


@router.put(
    "/business/setup",
    response_model=BusinessSetupResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def save_business_setup(
    body: BusinessSetupUpdateRequest,
    authenticated: CsrfProtected,
    dependencies: Management,
) -> BusinessSetupResponse:
    service: BusinessSetupService = dependencies.business_setup_service
    saved = service.save(
        authenticated.principal,
        business_name=body.business_name,
        your_name=body.your_name,
        email=body.email,
        service_description=body.service_description,
        ideal_client_profile=request_to_changes(
            body.ideal_client_profile, IdealClientProfileChanges
        ),
    )
    return response_from_domain(saved, BusinessSetupResponse)
