"""Immutable audit entry for one weekly reservation transition."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot


@dataclass(frozen=True, slots=True)
class WeeklyDigestDeliveryEvent:
    id: UUID
    delivery_id: UUID
    business_id: UUID
    delivery_version: int
    event_kind: Literal[
        "reserved",
        "content_prepared",
        "content_replaced",
        "sending_authorized",
        "sent",
        "unknown",
        "preparation_failed",
        "pre_send_failed",
        "empty",
        "suppressed",
        "unknown_resolved",
    ]
    recorded_at: datetime
    content_id: UUID | None = None
    actor_user_id: UUID | None = None
    reason: str | None = None
    outcome: Literal["sent", "failed"] | None = None
    accepted_at: datetime | None = None
    payload: JsonSnapshot = field(default_factory=lambda: JsonSnapshot({}))

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (self.id, self.delivery_id, self.business_id)
        ):
            raise ValidationDomainError("Digest event identities must be UUIDs")
        for value in (self.content_id, self.actor_user_id):
            if value is not None and not isinstance(value, UUID):
                raise ValidationDomainError("Digest event references must be UUIDs")
        if type(self.delivery_version) is not int or self.delivery_version < 1:
            raise ValidationDomainError("Digest event version must be positive")
        if type(self.event_kind) is not str or self.event_kind not in {
            "reserved",
            "content_prepared",
            "content_replaced",
            "sending_authorized",
            "sent",
            "unknown",
            "preparation_failed",
            "pre_send_failed",
            "empty",
            "suppressed",
            "unknown_resolved",
        }:
            raise ValidationDomainError("Invalid digest event kind")
        if (
            not isinstance(self.recorded_at, datetime)
            or self.recorded_at.tzinfo is None
            or self.recorded_at.utcoffset() is None
        ):
            raise ValidationDomainError("Digest event time must include a timezone")
        if self.accepted_at is not None and (
            not isinstance(self.accepted_at, datetime)
            or self.accepted_at.tzinfo is None
            or self.accepted_at.utcoffset() is None
            or self.accepted_at > self.recorded_at
        ):
            raise ValidationDomainError(
                "Actual handoff must precede its recorded observation"
            )
        if (
            self.event_kind
            in {
                "content_prepared",
                "content_replaced",
                "sending_authorized",
                "sent",
                "unknown",
                "pre_send_failed",
                "unknown_resolved",
            }
            and self.content_id is None
        ):
            raise ValidationDomainError("Digest event requires exact frozen content")
        if self.event_kind == "unknown_resolved":
            if (
                self.actor_user_id is None
                or type(self.reason) is not str
                or not self.reason.strip()
                or self.outcome not in {"sent", "failed"}
            ):
                raise ValidationDomainError(
                    "Unknown recovery requires actor, reason and explicit outcome"
                )
        elif self.outcome is not None:
            raise ValidationDomainError(
                "Only unknown recovery carries a resolution outcome"
            )
        confirmed = self.event_kind == "sent" or (
            self.event_kind == "unknown_resolved" and self.outcome == "sent"
        )
        if confirmed != (self.accepted_at is not None):
            raise ValidationDomainError(
                "Only confirmed delivery records actual handoff"
            )
        if not isinstance(self.payload, JsonSnapshot):
            raise ValidationDomainError("Digest event payload must be immutable JSON")
