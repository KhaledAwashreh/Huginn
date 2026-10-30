"""Application authentication, authorization, and throttling failures."""

from huginn.management.domain.errors.errors import ManagementDomainError


class AuthenticationError(ManagementDomainError):
    pass


class AuthorizationError(ManagementDomainError):
    pass


class RateLimitError(ManagementDomainError):
    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds
