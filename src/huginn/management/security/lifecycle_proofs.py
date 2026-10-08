"""Random proof material and digest storage per lifecycle design section 4."""

import hashlib
import re
import secrets


def generate_lifecycle_proof() -> str:
    return secrets.token_urlsafe(32)


def digest_lifecycle_proof(token: str) -> str:
    if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,1024}", token):
        raise ValueError("invalid lifecycle proof")
    return hashlib.sha256(token.encode("ascii")).hexdigest()
