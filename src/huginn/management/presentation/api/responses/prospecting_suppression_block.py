"""Canonical suppression block identity, state, attribution, and version."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class SuppressionBlockResponse(ResponseModel):
    id: UUID
    business_id: UUID
    company_id: UUID
    kind: Literal["cooldown", "pause", "rejection"]
    created_at: datetime
    effective_at: datetime
    created_by_user_id: UUID | None
    expires_at: datetime | None
    cleared_at: datetime | None
    cleared_by_user_id: UUID | None
    reason: str | None
    version: int
