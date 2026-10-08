"""ResetPasswordRequest strict HTTP body."""

from pydantic import Field, field_validator

from huginn.management.presentation.api.requests.common import RequestModel
from huginn.management.security.password_policy import (
    NEW_PASSWORD_MAX_LENGTH,
    NEW_PASSWORD_MIN_LENGTH,
)
from huginn.management.security.passwords import validate_new_password


class ResetPasswordRequest(RequestModel):
    token: str = Field(min_length=1, max_length=1024, repr=False)
    new_password: str = Field(
        min_length=NEW_PASSWORD_MIN_LENGTH,
        max_length=NEW_PASSWORD_MAX_LENGTH,
        repr=False,
    )

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        return validate_new_password(value).value
