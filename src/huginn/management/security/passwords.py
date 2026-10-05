"""Password validation and Werkzeug scrypt hash primitives."""

from werkzeug.security import check_password_hash, generate_password_hash

from huginn.management.security.password_policy import (
    PASSWORD_HASH_METHOD,
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
)


class Password:
    """A verbatim password that is redacted from its string representation."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("password must be text")
        if not PASSWORD_MIN_LENGTH <= len(value) <= PASSWORD_MAX_LENGTH:
            raise ValueError("password must be between 12 and 1024 characters")
        self._value = value

    def __setattr__(self, name: str, value: object) -> None:
        if hasattr(self, name):
            raise AttributeError("Password values are immutable")
        object.__setattr__(self, name, value)

    @property
    def value(self) -> str:
        """Return the verbatim value for validation or hashing operations."""

        return self._value

    def __repr__(self) -> str:
        return "Password(<redacted>)"

    def __str__(self) -> str:
        return "<redacted>"


def hash_password(password: Password, *, method: str = PASSWORD_HASH_METHOD) -> str:
    """Return a salted Werkzeug encoding for a validated password."""

    if not isinstance(password, Password):
        raise TypeError("password must be a Password value")
    return generate_password_hash(password.value, method=method)


def verify_password(password: Password, encoded_hash: str) -> bool:
    """Check a password against a Werkzeug encoded hash."""

    if not isinstance(password, Password):
        raise TypeError("password must be a Password value")
    try:
        return check_password_hash(encoded_hash, password.value)
    except TypeError, ValueError:
        return False


def needs_rehash(encoded_hash: str, canonical_method: str) -> bool:
    """Return whether the stored Werkzeug hash uses a noncanonical method."""

    return encoded_hash.partition("$")[0] != canonical_method
