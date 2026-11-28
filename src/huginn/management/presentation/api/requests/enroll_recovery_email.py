"""EnrollRecoveryEmailRequest strict HTTP body."""

from typing import Self

from pydantic import Field, model_validator

from huginn.management.presentation.api.primitives import Email
from huginn.management.presentation.api.requests.common import RequestModel


class EnrollRecoveryEmailRequest(RequestModel):
    email: Email | None = Field(default=None, repr=False)
    current_password: str | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def validate_change_credentials(self) -> Self:
        if (self.email is None) != (self.current_password is None):
            raise ValueError("An email change requires the email and current password")
        return self
