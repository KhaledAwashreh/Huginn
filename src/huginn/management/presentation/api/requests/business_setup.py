"""Required fields for the single profile save."""

from pydantic import field_validator

from huginn.management.presentation.api.primitives import Email, NonBlankText
from huginn.management.presentation.api.requests.common import RequestModel
from huginn.management.presentation.api.requests.ideal_client_profile import (
    IdealClientProfileCreateRequest,
)


class BusinessSetupUpdateRequest(RequestModel):
    business_name: NonBlankText
    your_name: NonBlankText
    email: Email | None = None
    service_description: NonBlankText
    ideal_client_profile: IdealClientProfileCreateRequest

    @field_validator("your_name")
    @classmethod
    def require_first_and_last_name(cls, value: str) -> str:
        if len(value.split(maxsplit=1)) < 2:
            raise ValueError("Enter your first and last name")
        return value
