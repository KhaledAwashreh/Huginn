"""Business profile response model."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.business_capability import (
    BusinessCapabilityResponse,
)
from huginn.management.presentation.api.responses.common import NonBlank, ResponseModel


class BusinessProfileResponse(ResponseModel):
    id: UUID
    owner_user_id: UUID
    name: NonBlank | None
    tagline: NonBlank | None
    website: NonBlank | None
    location: NonBlank | None
    description: NonBlank | None
    capabilities: list[BusinessCapabilityResponse] | None
    created_at: datetime
    updated_at: datetime
