"""Bind opt-out capabilities to a recipient and subscription generation."""

import hashlib
import hmac
import json
import re
from uuid import UUID


def digest_unsubscribe_token(
    key: str, user_id: UUID, recipient: str, version: str
) -> str:
    if not key or not recipient or not version:
        raise ValueError(
            "Digest signing key, recipient and subscription version are required"
        )
    payload = json.dumps(
        [
            "weekly-digest-unsubscribe/v2",
            str(user_id),
            recipient.strip().casefold(),
            version,
        ],
        separators=(",", ":"),
    )
    return hmac.new(key.encode(), payload.encode(), hashlib.sha256).hexdigest()


def valid_digest_unsubscribe(
    key: str, user_id: UUID, recipient: str, version: str, token: str
) -> bool:
    return (
        bool(key and recipient and version)
        and isinstance(token, str)
        and re.fullmatch(r"[0-9a-f]{64}", token) is not None
        and hmac.compare_digest(
            digest_unsubscribe_token(key, user_id, recipient, version), token
        )
    )
