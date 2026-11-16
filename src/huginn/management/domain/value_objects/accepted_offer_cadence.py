"""Repeat interval frozen at an offer's presentation/send authorization."""

from dataclasses import dataclass
from datetime import datetime

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True)
class AcceptedOfferCadence:
    repeat_interval_days: int
    preference_updated_at: datetime
    accepted_at: datetime

    def __post_init__(self) -> None:
        if type(self.repeat_interval_days) is not int or self.repeat_interval_days < 1:
            raise ValidationDomainError("Accepted repeat interval must be positive")
        for name in ("preference_updated_at", "accepted_at"):
            value = getattr(self, name)
            if (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValidationDomainError(f"{name} must include a timezone")
