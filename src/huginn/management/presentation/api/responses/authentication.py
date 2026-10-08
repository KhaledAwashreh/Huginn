"""Authentication response models."""

from datetime import datetime

from pydantic import Field

from huginn.management.presentation.api.responses.common import ResponseModel


class LoginResponse(ResponseModel):
    csrf_token: str = Field(repr=False)
    expires_at: datetime
