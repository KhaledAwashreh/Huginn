"""Signup response application value."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SignupResponse:
    message: str = "Check your email for next steps"
