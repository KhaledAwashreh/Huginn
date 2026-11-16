"""Business-owned recommendation cadence settings."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class BusinessRecommendationPreferences:
    business_id: UUID
    repeat_interval_days: int
    updated_at: datetime
