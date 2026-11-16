"""Immutable content version inside a Business's sole weekly reservation."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.weekly_digest_member import (
    WeeklyDigestMember,
)


@dataclass(frozen=True, slots=True)
class WeeklyDigestContent:
    id: UUID
    delivery_id: UUID
    business_id: UUID
    recipient_user_id: UUID
    version: int
    created_at: datetime
    subscription_updated_at: datetime
    recipient: str = field(repr=False)
    subject: str
    body: str = field(repr=False)
    message_id: str
    members: tuple[WeeklyDigestMember, ...]

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, UUID)
            for value in (
                self.id,
                self.delivery_id,
                self.business_id,
                self.recipient_user_id,
            )
        ):
            raise ValidationDomainError("Digest content requires exact UUIDs")
        if type(self.version) is not int or self.version < 1:
            raise ValidationDomainError("Digest content version must be positive")
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() is None
        ):
            raise ValidationDomainError(
                "Digest content creation time must include a timezone"
            )
        if (
            not isinstance(self.subscription_updated_at, datetime)
            or self.subscription_updated_at.tzinfo is None
            or self.subscription_updated_at.utcoffset() is None
        ):
            raise ValidationDomainError(
                "Digest consent version must include a timezone"
            )
        for name in ("recipient", "subject", "message_id"):
            value = getattr(self, name)
            if (
                type(value) is not str
                or not value.strip()
                or any(ord(char) < 32 or ord(char) == 127 for char in value)
            ):
                raise ValidationDomainError(
                    "Digest headers must be nonblank single lines"
                )
        if type(self.body) is not str or not self.body.strip():
            raise ValidationDomainError("Digest body is required")
        if (
            type(self.members) is not tuple
            or not 1 <= len(self.members) <= 7
            or any(
                not isinstance(member, WeeklyDigestMember) for member in self.members
            )
        ):
            raise ValidationDomainError(
                "Digest requires one to seven immutable members"
            )
        if tuple(member.position for member in self.members) != tuple(
            range(1, len(self.members) + 1)
        ):
            raise ValidationDomainError(
                "Digest members must have consecutive positions"
            )
        for name in ("company_id", "recommendation_id", "offer_cycle_id"):
            if len({getattr(member, name) for member in self.members}) != len(
                self.members
            ):
                raise ValidationDomainError("Digest members must be distinct")
