"""Purpose-separated opt-out signatures using the configured application key."""

import hashlib
import hmac
import re
from uuid import UUID


def digest_unsubscribe_token(key: str, user_id: UUID) -> str:
    if not key:
        raise ValueError("Digest signing key is required")
    return hmac.new(
        key.encode(), f"weekly-digest-unsubscribe/v1/{user_id}".encode(), hashlib.sha256
    ).hexdigest()


def valid_digest_unsubscribe(key: str, user_id: UUID, token: str) -> bool:
    return (
        bool(key)
        and isinstance(token, str)
        and re.fullmatch(r"[0-9a-f]{64}", token) is not None
        and hmac.compare_digest(digest_unsubscribe_token(key, user_id), token)
    )
