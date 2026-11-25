"""The saved single profile and its existing configuration records."""

from huginn.management.presentation.api.responses.business_profile import (
    BusinessProfileResponse,
)
from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.ideal_client_profile import (
    IdealClientProfileResponse,
)
from huginn.management.presentation.api.responses.service_offering import (
    ServiceOfferingResponse,
)
from huginn.management.presentation.api.responses.user import UserResponse


class BusinessSetupResponse(ResponseModel):
    business: BusinessProfileResponse
    user: UserResponse
    service_offering: ServiceOfferingResponse | None
    ideal_client_profile: IdealClientProfileResponse | None
