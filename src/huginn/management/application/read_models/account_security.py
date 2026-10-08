"""Account security information for application queries."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AccountSecurity:
    username: str
    email_verification_required: bool
    email_verified: bool
    recovery_email: str | None = field(repr=False)
