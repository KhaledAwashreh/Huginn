from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from huginn.elt.silver.types.source_context import SourceName


@dataclass(frozen=True)
class BronzeInput:
    source: SourceName
    stable_id: str
    payload: dict[str, object]
    fetched_at: datetime
    last_checked_at: datetime
