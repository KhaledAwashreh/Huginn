"""Current User response models."""

from datetime import datetime
from uuid import UUID

from huginn.management.primitives import E164Phone, Email, IanaTimezone, NonBlankText
from huginn.management.responses.common import ResponseModel


class UserResponse(ResponseModel):
    id: UUID
    first_name: NonBlankText
    last_name: NonBlankText
    email: Email
    phone_number: E164Phone
    country_of_residence: NonBlankText
    timezone: IanaTimezone | None
    created_at: datetime
    updated_at: datetime
