"""Expected account lifecycle domain failures."""

from huginn.management.domain.errors.errors import ValidationDomainError


class LifecycleProofError(ValidationDomainError):
    """Raised when recovery identity or proof values violate domain rules."""
