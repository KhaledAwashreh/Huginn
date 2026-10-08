"""Single-use proof data bound to one Account and lifecycle purpose."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from huginn.management.domain.errors.lifecycle import LifecycleProofError
from huginn.management.domain.value_objects.proof_purpose import ProofPurpose

_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s.]+(?:\.[^@\s.]+)+$")


def _require_aware(field_name: str, value: datetime) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise LifecycleProofError(f"invalid lifecycle field: {field_name}")


@dataclass(frozen=True)
class AccountLifecycleProof:
    id: UUID
    account_id: UUID
    token_digest: str = field(repr=False)
    purpose: ProofPurpose
    destination: str = field(repr=False)
    expires_at: datetime
    consumed_at: datetime | None
    superseded: bool
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise LifecycleProofError("invalid lifecycle field: id")
        if not isinstance(self.account_id, UUID):
            raise LifecycleProofError("invalid lifecycle field: account_id")
        if not isinstance(self.purpose, ProofPurpose):
            raise LifecycleProofError("invalid lifecycle field: purpose")
        if not isinstance(self.token_digest, str) or not re.fullmatch(
            r"[0-9a-f]{64}", self.token_digest
        ):
            raise LifecycleProofError("invalid lifecycle field: token_digest")
        if (
            not isinstance(self.destination, str)
            or not 3 <= len(self.destination) <= 254
            or not _EMAIL_PATTERN.fullmatch(self.destination)
        ):
            raise LifecycleProofError("invalid lifecycle field: destination")
        if type(self.superseded) is not bool:
            raise LifecycleProofError("invalid lifecycle field: superseded")
        _require_aware("created_at", self.created_at)
        _require_aware("expires_at", self.expires_at)
        if self.expires_at <= self.created_at:
            raise LifecycleProofError("invalid lifecycle field: expires_at")
        if self.consumed_at is not None:
            _require_aware("consumed_at", self.consumed_at)
            if self.consumed_at < self.created_at:
                raise LifecycleProofError("invalid lifecycle field: consumed_at")
