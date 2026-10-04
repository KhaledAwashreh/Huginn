"""Application authentication, authorization, and throttling failures."""

from huginn.management.domain.errors.errors import ManagementDomainError


class AuthenticationError(ManagementDomainError):
    pass


class AuthorizationError(ManagementDomainError):
    pass


class RateLimitError(ManagementDomainError):
    pass
