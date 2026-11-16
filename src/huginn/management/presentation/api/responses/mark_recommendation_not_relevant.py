"""Immutable rejection result and its independently remaining blockers."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class MarkRecommendationNotRelevantResponse(ResponseModel):
    recommendation_id: UUID
    recommendation_version: int
    recommendation_status: str
    suppression_block_id: UUID
    resolved_at: datetime
    reason: str | None
    remaining_blockers: list[str]
