import re
from dataclasses import dataclass

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True)
class CommandIdentity:
    key: str
    payload_fingerprint: str

    def __post_init__(self) -> None:
        if not isinstance(self.key, str) or not self.key.strip() or len(self.key) > 200:
            raise ValidationDomainError("Invalid command idempotency key")
        if (
            not isinstance(self.payload_fingerprint, str)
            or re.fullmatch(r"[0-9a-f]{64}", self.payload_fingerprint) is None
        ):
            raise ValidationDomainError(
                "Payload fingerprint must be a SHA-256 hex digest"
            )
