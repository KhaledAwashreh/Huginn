"""Ingestion data shapes. See architecture document section 5.

Separated from `ports.py` so the protocols file holds contracts only and
the data a contract passes around has its own home, consistent with the
`models.py` / `ports.py` / `repositories/` split every ELT stage uses.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RawRecord:
    """One fetched record, prior to any Bronze-side hashing or storage.

    `stable_id` is the source-native identifier used for the
    `(source, stable_id)` uniqueness key at Bronze (see architecture
    document section 4.1). `payload` is the raw, unmodified data as
    fetched, stored as-is in Bronze's `payload` column.
    """

    stable_id: str
    payload: dict
