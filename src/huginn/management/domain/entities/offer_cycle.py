from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.offer_cycle_status import OfferCycleStatus


@dataclass(frozen=True)
class OfferCycle:
    id: UUID
    business_id: UUID
    company_id: UUID
    recommendation_id: UUID
    selected_revision_id: UUID
    idempotency_key: str
    payload_fingerprint: str
    status: OfferCycleStatus
    created_at: datetime
    updated_at: datetime
    claim_token: str | None = None
    lease_expires_at: datetime | None = None
    sending_started_at: datetime | None = None
    settled_at: datetime | None = None
    presented_at: datetime | None = None

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (
                self.id,
                self.business_id,
                self.company_id,
                self.recommendation_id,
                self.selected_revision_id,
            )
        ):
            raise ValidationDomainError("Offer cycle identities must be UUIDs")
        CommandIdentity(self.idempotency_key, self.payload_fingerprint)
        if not isinstance(self.status, OfferCycleStatus):
            raise ValidationDomainError("Offer cycle status must use its domain value")
        for name in (
            "created_at",
            "updated_at",
            "lease_expires_at",
            "sending_started_at",
            "settled_at",
            "presented_at",
        ):
            value = getattr(self, name)
            if value is not None:
                _aware(value, name)
        if self.status.value == "preparing":
            if not self.claim_token or self.lease_expires_at is None:
                raise ValidationDomainError(
                    "Preparing offer claims require a token and finite lease"
                )
            if self.lease_expires_at <= self.created_at:
                raise ValidationDomainError(
                    "Preparing offer lease must expire after claim creation"
                )
        elif self.lease_expires_at is not None:
            raise ValidationDomainError(
                "Only a preparing offer claim has an expiring lease"
            )
        if (
            self.status.value in {"sending", "unknown"}
            and self.sending_started_at is None
        ):
            raise ValidationDomainError(
                "Sending and unknown cycles require a send-start time"
            )
        if (self.status.value == "confirmed") != (self.presented_at is not None):
            raise ValidationDomainError(
                "Only confirmed cycles record presentation time"
            )
        if (
            self.status.value in {"confirmed", "abandoned", "unknown"}
            and self.settled_at is None
        ):
            raise ValidationDomainError("Settled cycles require a settlement time")
        if self.status.value == "confirmed" and self.presented_at > self.settled_at:
            raise ValidationDomainError(
                "Presentation cannot occur after settlement is recorded"
            )
        if self.status.value == "preparing" and any(
            value is not None
            for value in (self.sending_started_at, self.settled_at, self.presented_at)
        ):
            raise ValidationDomainError(
                "Preparing cycles have not started sending or presented"
            )
        if (
            self.status.value in {"sending", "unknown"}
            and self.presented_at is not None
        ):
            raise ValidationDomainError(
                "Unconfirmed delivery cannot claim presentation"
            )


def _aware(value: datetime, name: str) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise ValidationDomainError(f"{name} must include a timezone")
