"""Service offering response models."""

from datetime import datetime
from uuid import UUID

from huginn.management.responses.common import NonBlank, ResponseModel


class ServiceOfferingResponse(ResponseModel):
    id: UUID
    user_id: UUID
    name: NonBlank
    description: NonBlank
    created_at: datetime
    updated_at: datetime
