"""Current Business cadence and its comparison version."""

from datetime import datetime
from uuid import UUID

from huginn.management.presentation.api.responses.common import ResponseModel


class BusinessRecommendationPreferencesResponse(ResponseModel):
    business_id: UUID
    repeat_interval_days: int
    updated_at: datetime
