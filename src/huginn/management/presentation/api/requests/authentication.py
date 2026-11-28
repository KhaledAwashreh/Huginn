"""Authentication request bodies."""

from typing import Self

from pydantic import Field, model_validator

from huginn.management.presentation.api.requests.common import RequestModel


class LoginRequest(RequestModel):
    username: str | None = Field(default=None, min_length=1)
    email: str | None = Field(default=None, min_length=1, max_length=254)
    password: str

    @model_validator(mode="after")
    def validate_identifier(self) -> Self:
        if (self.username is None) == (self.email is None):
            raise ValueError("Supply either an email or a username")
        return self


class PasswordChangeRequest(RequestModel):
    current_password: str
    new_password: str
