"""Authentication response models."""

from datetime import datetime

from huginn.management.responses.common import ResponseModel


class LoginResponse(ResponseModel):
    csrf_token: str
    expires_at: datetime
