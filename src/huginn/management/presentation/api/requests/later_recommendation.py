"""Explicit duration and current pause/preference comparison for replacement."""

from typing import Annotated, Literal

from pydantic import Field

from huginn.management.presentation.api.requests.common import (
    RequestTimestamp,
    RequestUUID,
)
from huginn.management.presentation.api.requests.save_recommendation import (
    SaveRecommendationRequest,
)


class LaterRecommendationRequest(SaveRecommendationRequest):
    expected_recommendation_version: Annotated[int, Field(ge=1)]
    pause_choice: Literal["x1", "x2", "x3", "x4", "indefinite"]
    expected_repeat_interval_days: Annotated[int, Field(ge=1)]
    expected_preference_updated_at: RequestTimestamp
    expected_pause_id: RequestUUID | None
    expected_pause_version: Annotated[int, Field(ge=1)] | None
