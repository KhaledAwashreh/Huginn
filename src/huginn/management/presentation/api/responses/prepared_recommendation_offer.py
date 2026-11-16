"""Preparation lifecycle truth, including a consumed or expired retry."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class PreparedRecommendationOfferResponse(ResponseModel):
    offer_cycle_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    status: Literal["preparing", "sending", "confirmed", "abandoned", "unknown"]
    claim_token: str | None
    lease_expires_at: datetime | None
    presented_at: datetime | None
