"""HTTP projection of the session bootstrap application response."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from huginn.management.presentation.api.responses.common import ResponseModel


class CurrentSessionResponse(ResponseModel):
    account_id: UUID
    user_id: UUID
    csrf_token: str = Field(repr=False)
    expires_at: datetime
    role: str
