"""Strict database boundary for current Gold company fields."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CurrentCompanyRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    id: UUID
    name: str
    domain: str
    business_sector: list[str] | None
    country: str | None
    company_scale: str | None
    company_status: str | None
