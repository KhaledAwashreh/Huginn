"""Strict database boundary for a current Gold signal."""

from datetime import datetime
from typing import Literal
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
    occurred_at: datetime | None
    ingested_at: datetime
    observation_id: UUID
    observed_at: datetime
    evidence_kind: Literal["hiring", "directory_context"]
    hiring_state: Literal["true", "false", "unknown", "not_applicable"]
