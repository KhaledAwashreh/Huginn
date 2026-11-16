"""Intent to pause an exact open recommendation for a captured duration."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.pause_choice import PauseChoice


@dataclass(frozen=True, slots=True)
class LaterRecommendationRequest:
    recommendation_id: UUID
    assessment_revision_id: UUID
    expected_recommendation_version: int
    pause_choice: PauseChoice
    expected_repeat_interval_days: int
    expected_preference_updated_at: datetime
    expected_pause_id: UUID | None
    expected_pause_version: int | None
    request_key: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.recommendation_id, UUID) or not isinstance(
            self.assessment_revision_id, UUID
        ):
            raise ValidationDomainError(
                "Later requires recommendation and revision IDs"
            )
        if (
            type(self.expected_recommendation_version) is not int
            or self.expected_recommendation_version < 1
        ):
            raise ValidationDomainError(
                "Expected recommendation version must be positive"
            )
        if not isinstance(self.pause_choice, PauseChoice):
            raise ValidationDomainError("Later duration must use its domain value")
        if (
            type(self.expected_repeat_interval_days) is not int
            or self.expected_repeat_interval_days < 1
        ):
            raise ValidationDomainError("Expected repeat interval must be positive")
        if (
            not isinstance(self.expected_preference_updated_at, datetime)
            or self.expected_preference_updated_at.tzinfo is None
            or self.expected_preference_updated_at.utcoffset() is None
        ):
            raise ValidationDomainError(
                "Preference snapshot time must include a timezone"
            )
        if (self.expected_pause_id is None) != (self.expected_pause_version is None):
            raise ValidationDomainError(
                "Expected pause ID and version must be supplied together"
            )
        if self.expected_pause_id is not None and not isinstance(
            self.expected_pause_id, UUID
        ):
            raise ValidationDomainError("Expected pause ID must be a UUID")
        if self.expected_pause_version is not None and (
            type(self.expected_pause_version) is not int
            or self.expected_pause_version < 1
        ):
            raise ValidationDomainError("Expected pause version must be positive")
        if type(self.request_key) is not str or not self.request_key.strip():
            raise ValidationDomainError("Request key is required")
        if self.reason is not None and type(self.reason) is not str:
            raise ValidationDomainError("Mute reason must be text")
