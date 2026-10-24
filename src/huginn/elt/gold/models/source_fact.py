from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class SourceFact:
    company_id: UUID
    source: str
    stable_id: str
    observation_id: UUID
    snapshot_id: UUID
    raw_token: str | None
    resolution_token: str
    context_version: str
    policy_version: str
    occurred_at: datetime | None
    source_fields: str
