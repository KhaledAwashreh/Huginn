"""Account security information for application queries."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AccountSecurity:
    account_email: str = field(repr=False)
    pending_email: str | None = field(repr=False)
    email_verification_required: bool
    email_verified: bool
