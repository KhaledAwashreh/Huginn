"""Discovery strategy response models."""

from datetime import datetime
from uuid import UUID

from huginn.management.responses.common import NonBlank, ResponseModel


class DiscoveryStrategyResponse(ResponseModel):
    id: UUID
    user_id: UUID
    name: NonBlank
    service_offering_id: UUID
    ideal_client_profile_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
