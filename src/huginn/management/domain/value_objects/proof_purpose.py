"""Purposes assigned to single-use account lifecycle proofs."""

from enum import StrEnum


class ProofPurpose(StrEnum):
    VERIFY_EMAIL = "verify_email"
    RESET_PASSWORD = "reset_password"
