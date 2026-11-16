"""The immutable actual presentation and accepted cooldown expiry."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class ConfirmedRecommendationOfferResponse(ResponseModel):
    offer_cycle_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    presented_at: datetime
    cooldown_expires_at: datetime
