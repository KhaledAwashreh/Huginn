from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.elt.silver.types.source_context import SourceName


@dataclass(frozen=True)
class LifecycleInput:
    source: SourceName
    stable_id: str
    payload: dict[str, object]
    raw_token: str
    resolution_token: str
    resolved_company_key: str | None
    key_derivation: str | None
    company_id: UUID | None
    fetched_at: datetime
    last_checked_at: datetime
