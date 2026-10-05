"""Domain-level failures independent of HTTP and persistence frameworks."""


class ManagementDomainError(Exception):
    """Base class for expected management use-case failures."""


class ValidationDomainError(ManagementDomainError):
    pass


class NotFoundError(ManagementDomainError):
    pass


class ConflictError(ManagementDomainError):
    pass
