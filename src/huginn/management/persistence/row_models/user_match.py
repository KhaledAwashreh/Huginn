"""Strict database boundary for an owned match joined to current company."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserMatchRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    id: UUID
    user_id: UUID
    status: Literal["new", "contacted", "responded", "dismissed", "converted"]
    notes: str | None
    created_at: datetime
    updated_at: datetime
    company_id: UUID
    company_name: str
    company_domain: str
    business_sector: list[str] | None
    country: str | None
    company_scale: str | None
    company_status: str | None
