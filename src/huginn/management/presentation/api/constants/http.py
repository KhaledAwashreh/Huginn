"""Shared HTTP boundary defaults and sensitive field names."""

DEFAULT_SESSION_COOKIE_NAME = "huginn_management_session"
DEFAULT_COOKIE_SAMESITE = "Lax"
SENSITIVE_FIELDS = frozenset(
    {
        "password",
        "current_password",
        "new_password",
        "password_hash",
        "token_digest",
        "csrf_digest",
    }
)
