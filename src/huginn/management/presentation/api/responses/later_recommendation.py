"""Accepted pause times and cadence, including an explicitly replaced pause."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class LaterRecommendationResponse(ResponseModel):
    recommendation_id: UUID
    recommendation_version: int
    suppression_block_id: UUID
    replaced_pause_id: UUID | None
    pause_choice: str
    repeat_interval_days: int
    preference_updated_at: datetime
    selected_at: datetime
    expires_at: datetime | None
    remaining_blockers: list[str]
