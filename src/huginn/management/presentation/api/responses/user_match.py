"""Owned match response composed with current company context."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel
from huginn.management.presentation.api.responses.current_company import (
    CurrentCompanyResponse,
)


class UserMatchResponse(ResponseModel):
    id: UUID
    status: str
    notes: str | None
    created_at: datetime
    updated_at: datetime
    company: CurrentCompanyResponse
