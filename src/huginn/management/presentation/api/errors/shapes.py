"""Stable public error envelope shapes and domain error status mapping."""

from dataclasses import dataclass
from typing import Any

from huginn.management.application.errors.errors import (
    AuthenticationError,
    AuthorizationError,
    RateLimitError,
)
from huginn.management.domain.errors.errors import (
    ConflictError,
    ManagementDomainError,
    NotFoundError,
    ValidationDomainError,
)


@dataclass(frozen=True)
class ErrorShape:
    status_code: int
    body: dict[str, Any]


ERROR_MESSAGES_BY_STATUS = {
    400: ("malformed_json", "Malformed JSON request"),
    401: ("authentication_error", "Request could not be completed"),
    403: ("authorization_error", "Request could not be completed"),
    404: ("not_found", "Request could not be completed"),
    409: ("conflict", "Request could not be completed"),
    422: ("validation_error", "Request validation failed"),
    429: ("rate_limited", "Request could not be completed"),
}


def error_shape(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
) -> ErrorShape:
    return ErrorShape(
        status_code=status_code,
        body={
            "error": {
                "code": code,
                "message": message,
                "details": details if details is not None else [],
            }
        },
    )


def error_shape_for_status(status_code: int) -> ErrorShape:
    if status_code == 503:
        return error_shape(
            503, "service_unavailable", "The service is temporarily unavailable"
        )
    code, message = ERROR_MESSAGES_BY_STATUS.get(
        status_code,
        (f"http_{status_code}", "Request could not be completed"),
    )
    if status_code >= 500:
        return error_shape(500, "internal_error", "An unexpected error occurred")
    return error_shape(status_code, code, message)


def native_validation_shape(details: list[dict[str, Any]]) -> ErrorShape:
    """Return sanitized FastAPI-style validation details without an error envelope."""
    return ErrorShape(status_code=422, body={"detail": details})


def domain_error_shape(error: ManagementDomainError) -> ErrorShape:
    status = 500
    if isinstance(error, AuthenticationError):
        status = 401
    elif isinstance(error, AuthorizationError):
        status = 403
    elif isinstance(error, NotFoundError):
        status = 404
    elif isinstance(error, ConflictError):
        status = 409
    elif isinstance(error, ValidationDomainError):
        status = 422
    elif isinstance(error, RateLimitError):
        status = 429
    return error_shape_for_status(status)
