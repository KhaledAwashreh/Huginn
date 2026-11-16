"""Immutable reversal/cancellation result; each clears only its own block."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class ClearRecommendationSuppressionResponse(ResponseModel):
    suppression_block_id: UUID
    block_version: int
    cleared_at: datetime
    remaining_blockers: list[str]
