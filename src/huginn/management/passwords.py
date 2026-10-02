"""Password value validation and Werkzeug scrypt adapters."""

from werkzeug.security import check_password_hash, generate_password_hash


class Password:
    """A verbatim password that is redacted from its string representation."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        if not isinstance(value, str):
            raise TypeError("password must be text")
        if not 12 <= len(value) <= 1024:
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


def hash_password(password: Password, *, method: str = "scrypt") -> str:
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
