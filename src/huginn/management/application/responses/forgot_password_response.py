"""ForgotPassword response application value."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ForgotPasswordResponse:
    message: str = "Check your email for next steps"
