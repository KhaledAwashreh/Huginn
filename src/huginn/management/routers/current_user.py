"""Self-service User and ProfessionalProfile endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from huginn.management.dependencies.authentication import Authenticated, CsrfProtected
from huginn.management.dependencies.services import Management
from huginn.management.domain.professional_profile import ProfessionalProfileChanges
from huginn.management.domain.user import UserChanges
from huginn.management.openapi_responses import error_responses
from huginn.management.requests.professional_profile import (
    ProfessionalProfileUpdateRequest,
)
from huginn.management.requests.user import UserUpdateRequest
from huginn.management.responses.professional_profile import (
    ProfessionalProfileResponse,
)
from huginn.management.responses.user import UserResponse
from huginn.management.services.user_profile import UserProfileService
from huginn.management.transport import request_to_changes, response_from_domain

router = APIRouter(prefix="/api/v1", tags=["current-user"])


def get_user_profile_service(dependencies: Management) -> UserProfileService:
    return dependencies.user_profile_service


UserProfile = Annotated[UserProfileService, Depends(get_user_profile_service)]


@router.get("/me", response_model=UserResponse, responses=error_responses(401, 404))
def get_current_user(
    authenticated: Authenticated, service: UserProfile
) -> UserResponse:
    user = service.get_user(authenticated.principal)
    return response_from_domain(user, UserResponse)


@router.patch(
    "/me",
    response_model=UserResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def update_current_user(
    body: UserUpdateRequest,
    authenticated: CsrfProtected,
    service: UserProfile,
) -> UserResponse:
    changes = request_to_changes(body, UserChanges)
    user = service.update_user(authenticated.principal, changes)
    return response_from_domain(user, UserResponse)


@router.get(
    "/me/professional-profile",
    response_model=ProfessionalProfileResponse,
    responses=error_responses(401, 404),
)
def get_current_professional_profile(
    authenticated: Authenticated, service: UserProfile
) -> ProfessionalProfileResponse:
    profile = service.get_profile(authenticated.principal)
    return response_from_domain(profile, ProfessionalProfileResponse)


@router.patch(
    "/me/professional-profile",
    response_model=ProfessionalProfileResponse,
    responses=error_responses(400, 401, 403, 404, 409, 422),
)
def update_current_professional_profile(
    body: ProfessionalProfileUpdateRequest,
    authenticated: CsrfProtected,
    service: UserProfile,
) -> ProfessionalProfileResponse:
    changes = request_to_changes(body, ProfessionalProfileChanges)
    profile = service.update_profile(authenticated.principal, changes)
    return response_from_domain(profile, ProfessionalProfileResponse)
