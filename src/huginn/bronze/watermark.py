"""Content-hash watermark. See architecture document section 4.1.

Neither HN's Firebase API nor YC's Algolia backend offers a reliable
"give me only what changed" cursor, so a SHA-256 hash over a deliberately
chosen, lightly normalized subset of each source's fields stands in for
one: `(source, stable_id, content_hash)` where a native `updated_at`
would otherwise sit.
"""

from __future__ import annotations

import hashlib


def normalize_field(value: str) -> str:
    """Light normalization for hashing purposes only: collapse whitespace,
    lowercase. Does not touch the stored raw payload, only the value fed
    into the hash (architecture document section 4.1).
    """
    return " ".join(value.split()).lower()


def compute_content_hash(payload: dict, stable_fields: list[str]) -> str:
    """SHA-256 over a deliberately chosen, lightly normalized subset of a
    payload's fields.

    `stable_fields` is chosen per source by the adapter: the fields that
    represent "the content that matters" for that source, excluding
    volatile noise (e.g. an Algolia relevance score) that would otherwise
    make every fetch look changed. See architecture document section 4.1.
    """
    normalized_values = [
        normalize_field(str(payload.get(field, ""))) for field in sorted(stable_fields)
    ]
    joined = "\x1f".join(normalized_values)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()
