"""Strict collected criterion query row."""

from pydantic import BaseModel, ConfigDict, Field


class ConfigurationOptionRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    value: str = Field(min_length=1)
    company_count: int = Field(ge=0)
