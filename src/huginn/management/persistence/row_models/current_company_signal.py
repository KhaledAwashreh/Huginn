"""Strict database boundary for a current Gold signal."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CurrentCompanySignalRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    id: UUID
    signal_type: str
    source: str
    source_url: str | None
    description: str | None
    stage: str | None
    occurred_at: datetime
    ingested_at: datetime
