"""ForgotPassword request application value."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ForgotPasswordRequest:
    email: str = field(repr=False)
    client_ip: str = field(repr=False)
