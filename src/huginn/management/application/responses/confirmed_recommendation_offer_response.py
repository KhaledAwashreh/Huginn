"""Immutable outcome of a confirmed in-app recommendation presentation."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class ConfirmedRecommendationOfferResponse:
    offer_cycle_id: UUID
    recommendation_id: UUID
    assessment_revision_id: UUID
    presented_at: datetime
    cooldown_expires_at: datetime
