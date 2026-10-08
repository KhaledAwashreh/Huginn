"""Expected failures from public account lifecycle use cases."""

from huginn.management.application.errors.errors import RateLimitError
from huginn.management.domain.errors.errors import (
    ConflictError,
    ManagementDomainError,
)


class LifecycleConflictError(ConflictError):
    """A lifecycle operation conflicts with current account state."""


class LifecycleRateLimitError(RateLimitError):
    """A lifecycle operation exceeded an admission limit."""

    def __init__(self, message: str, retry_after_seconds: int) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class LifecycleIntegrityError(ManagementDomainError):
    """Persisted lifecycle data is inconsistent or cannot be trusted."""
