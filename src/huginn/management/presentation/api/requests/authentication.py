"""Authentication request bodies."""

from pydantic import Field

from huginn.management.presentation.api.requests.common import RequestModel


class LoginRequest(RequestModel):
    username: str = Field(min_length=1)
    password: str


class PasswordChangeRequest(RequestModel):
    current_password: str
    new_password: str
