"""Recovery address and verification state bound to an Account."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.value_objects.verification_state import (
    VerificationState,
)

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


def _validate_email(field_name: str, value: str | None) -> None:
    if value is not None and (
        not isinstance(value, str)
        or not 3 <= len(value) <= 254
        or not _EMAIL_PATTERN.fullmatch(value)
    ):
        raise LifecycleProofError(f"invalid lifecycle field: {field_name}")


def _require_aware(field_name: str, value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise LifecycleProofError(f"invalid lifecycle field: {field_name}")


@dataclass(frozen=True)
class AccountRecoveryIdentity:
    account_id: UUID
    verification_required: bool
    pending_email: str | None = field(repr=False)
    verified_email: str | None = field(repr=False)
    verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.account_id, UUID):
            raise LifecycleProofError("invalid lifecycle field: account_id")
        if type(self.verification_required) is not bool:
            raise LifecycleProofError("invalid lifecycle field: verification_required")
        _validate_email("pending_email", self.pending_email)
        _validate_email("verified_email", self.verified_email)
        _require_aware("created_at", self.created_at)
        _require_aware("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise LifecycleProofError("invalid lifecycle field: updated_at")

        if self.verified_at is not None:
            _require_aware("verified_at", self.verified_at)
        if (self.verified_email is None) != (self.verified_at is None):
            raise LifecycleProofError("invalid lifecycle field: verified_at")
        if self.pending_email is not None and self.verified_email is not None:
            raise LifecycleProofError("invalid lifecycle field: pending_email")
        if (
            self.verification_required
            and self.pending_email is None
            and self.verified_email is None
        ):
            raise LifecycleProofError("invalid lifecycle field: pending_email")

    @property
    def verification_state(self) -> VerificationState:
        if self.verified_email is not None:
            return VerificationState.VERIFIED
        if self.pending_email is not None:
            return VerificationState.PENDING
        return VerificationState.TRUSTED
