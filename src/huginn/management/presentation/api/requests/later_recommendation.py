"""Explicit duration and current pause/preference comparison for replacement."""

from typing import Annotated

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
    pause_choice: Annotated[
        str,
        Field(
            pattern=(
                r"^(x[1-4]|indefinite|d(?:[1-9]|[1-9][0-9]|[12][0-9]{2}"
                r"|3[0-5][0-9]|36[0-5]))$"
            )
        ),
    ]
    expected_repeat_interval_days: Annotated[int, Field(ge=1)]
    expected_preference_updated_at: RequestTimestamp
    expected_pause_id: RequestUUID | None
    expected_pause_version: Annotated[int, Field(ge=1)] | None
    reason: Annotated[str, Field(max_length=2000)] | None = None
