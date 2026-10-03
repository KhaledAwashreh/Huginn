"""Opaque token generation and one-way digest primitives."""

import hashlib
import secrets

from huginn.management.constants.authentication import SESSION_TOKEN_BYTES


def generate_token() -> str:
    """Generate a URL-safe opaque token suitable for a browser credential."""

    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def digest_token(token: str) -> str:
    """Return the SHA-256 hex digest used for persistence and lookup."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()
