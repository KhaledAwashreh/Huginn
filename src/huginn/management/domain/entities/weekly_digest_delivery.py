"""Business/week reservation with separately recorded SMTP chronology."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True, slots=True)
class WeeklyDigestDelivery:
    id: UUID
    business_id: UUID
    recipient_user_id: UUID
    week_start: date
    created_at: datetime
    state: Literal[
        "preparing", "sending", "sent", "unknown", "empty", "failed", "suppressed"
    ] = "preparing"
    version: int = 1
    current_content_id: UUID | None = None
    sending_started_at: datetime | None = None
    settled_at: datetime | None = None
    accepted_at: datetime | None = None

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (self.id, self.business_id, self.recipient_user_id)
        ):
            raise ValidationDomainError("Digest reservation identities must be UUIDs")
        if self.current_content_id is not None and not isinstance(
            self.current_content_id, UUID
        ):
            raise ValidationDomainError("Digest content identity must be a UUID")
        if type(self.week_start) is not date or self.week_start.weekday() != 0:
            raise ValidationDomainError(
                "Digest reservation requires a Monday week start"
            )
        if type(self.version) is not int or self.version < 1:
            raise ValidationDomainError("Digest reservation version must be positive")
        if type(self.state) is not str or self.state not in {
            "preparing",
            "sending",
            "sent",
            "unknown",
            "empty",
            "failed",
            "suppressed",
        }:
            raise ValidationDomainError("Invalid digest reservation state")
        for name in ("created_at", "sending_started_at", "settled_at", "accepted_at"):
            value = getattr(self, name)
            if (name == "created_at" or value is not None) and (
                not isinstance(value, datetime)
                or value.tzinfo is None
                or value.utcoffset() is None
            ):
                raise ValidationDomainError("Digest times must include a timezone")
        if self.state in {"sending", "sent", "unknown"} and (
            self.current_content_id is None or self.sending_started_at is None
        ):
            raise ValidationDomainError(
                "Transport requires frozen content and authorization time"
            )
        if (self.state in {"preparing", "sending"}) != (self.settled_at is None):
            raise ValidationDomainError("Digest settlement time must match its state")
        if (self.state == "sent") != (self.accepted_at is not None):
            raise ValidationDomainError(
                "Only a sent digest has acknowledged acceptance"
            )
        if (
            self.state in {"preparing", "empty", "suppressed"}
            and self.sending_started_at is not None
        ):
            raise ValidationDomainError("Unsent digest has no send authorization")
        if (
            self.sending_started_at is not None
            and self.sending_started_at < self.created_at
        ):
            raise ValidationDomainError("Send authorization cannot precede reservation")
        if self.settled_at is not None and self.settled_at < (
            self.sending_started_at or self.created_at
        ):
            raise ValidationDomainError(
                "Settlement cannot precede reservation or authorization"
            )
        if (
            self.accepted_at is not None
            and not self.sending_started_at <= self.accepted_at <= self.settled_at
        ):
            raise ValidationDomainError(
                "Acceptance must lie between authorization and settlement"
            )
