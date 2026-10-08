"""VerifyEmail response application value."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerifyEmailResponse:
    pass
