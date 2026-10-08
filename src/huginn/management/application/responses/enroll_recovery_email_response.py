"""Lifecycle application response."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EnrollRecoveryEmailResponse:
    message: str = "Check your email for next steps"
