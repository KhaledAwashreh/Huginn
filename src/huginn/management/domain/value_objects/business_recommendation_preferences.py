"""Business recommendation cadence update values."""

from dataclasses import dataclass

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True)
class BusinessRecommendationPreferencesChanges:
    repeat_interval_days: int

    def __post_init__(self) -> None:
        if type(self.repeat_interval_days) is not int or self.repeat_interval_days < 1:
            raise ValidationDomainError(
                "Repeat interval must be a positive number of days"
            )
