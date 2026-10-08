"""Email verification states derived from recovery identity data."""

from enum import StrEnum


class VerificationState(StrEnum):
    TRUSTED = "trusted"
    PENDING = "pending"
    VERIFIED = "verified"
