"""ResetPassword request application value."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ResetPasswordRequest:
    token: str = field(repr=False)
    new_password: str = field(repr=False)
    client_ip: str = field(repr=False)
