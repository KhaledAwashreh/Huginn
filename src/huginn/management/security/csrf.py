"""Stable CSRF derivation for the web-ui-foundation session contract."""

import hashlib
import hmac

from huginn.management.security.csrf_policy import CSRF_CONTEXT_VERSION


def derive_csrf_token(raw_token: str) -> str:
    return hmac.new(
        raw_token.encode("utf-8"),
        CSRF_CONTEXT_VERSION.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
