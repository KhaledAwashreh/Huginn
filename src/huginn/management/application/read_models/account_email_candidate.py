"""Identity fields needed for the account email cutover audit."""

from dataclasses import dataclass, field
from uuid import UUID

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.services.identity_validation import normalized_email


@dataclass(frozen=True, slots=True)
class AccountEmailCandidate:
    account_id: UUID
    has_user: bool
    verification_required: bool | None
    contact_email: str | None = field(repr=False)
    pending_email: str | None = field(repr=False)
    verified_email: str | None = field(repr=False)

    @property
    def sign_in_email(self) -> str | None:
        if self.verified_email is not None:
            candidate = self.verified_email
        elif self.verification_required:
            candidate = self.pending_email
        else:
            candidate = self.contact_email
        try:
            return normalized_email(candidate)
        except ValidationDomainError:
            return None
