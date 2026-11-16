"""Explicit Business repeat-interval update intent."""

from pydantic import model_validator

from huginn.management.presentation.api.requests.common import PatchRequest


class BusinessRecommendationPreferencesUpdateRequest(PatchRequest):
    repeat_interval_days: int

    @model_validator(mode="after")
    def require_positive_interval(self):
        if self.repeat_interval_days < 1:
            raise ValueError("repeat_interval_days must be positive")
        return self
