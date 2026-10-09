"""Strict collected company query row."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CompanyOptionRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    id: UUID
    name: str = Field(min_length=1)
    domain: str | None
