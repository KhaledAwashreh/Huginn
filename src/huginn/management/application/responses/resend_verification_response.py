"""ResendVerification response application value."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResendVerificationResponse:
    message: str = "Check your email for next steps"
