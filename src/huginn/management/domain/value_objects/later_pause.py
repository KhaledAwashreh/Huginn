from dataclasses import dataclass
from datetime import datetime, timedelta

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.pause_choice import PauseChoice


@dataclass(frozen=True)
class LaterPause:
    choice: PauseChoice
    repeat_interval_days: int
    preference_updated_at: datetime
    selected_at: datetime
    expires_at: datetime | None

    def __post_init__(self) -> None:
        if not isinstance(self.choice, PauseChoice):
            raise ValidationDomainError("Pause snapshot requires an approved choice")
        for name in ("preference_updated_at", "selected_at", "expires_at"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValidationDomainError(f"{name} must include a timezone")
        if type(self.repeat_interval_days) is not int or self.repeat_interval_days < 1:
            raise ValidationDomainError("Repeat interval must be positive")
        if self.preference_updated_at > self.selected_at:
            raise ValidationDomainError("Pause cannot use a future preference version")
        if self.choice.value == "indefinite":
            if self.expires_at is not None:
                raise ValidationDomainError("Indefinite pauses do not expire")
        elif self.choice.days is not None:
            expected = self.selected_at + timedelta(days=self.choice.days)
            if self.expires_at != expected:
                raise ValidationDomainError(
                    "Pause expiry must preserve its selected duration"
                )
        else:
            multiplier = int(self.choice.value[1:])
            expected = self.selected_at + timedelta(
                days=multiplier * self.repeat_interval_days
            )
            if self.expires_at != expected:
                raise ValidationDomainError(
                    "Pause expiry must preserve its selected duration"
                )
