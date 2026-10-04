"""Pydantic models for validating JSONB and mapped persistence rows.

These shapes protect the repository boundary from malformed persisted data.
They are deliberately private to PostgreSQL and are not HTTP request or
response models.
"""

from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

_NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
_Month = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]


class _RowModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class SkillRow(_RowModel):
    name: _NonBlank


class ExperienceRow(_RowModel):
    organization: _NonBlank
    role: _NonBlank
    summary: _NonBlank | None = None
    start_month: _Month | None = None
    end_month: _Month | None = None
    is_current: bool = False

    @model_validator(mode="after")
    def validate_months(self) -> Self:
        for value in (self.start_month, self.end_month):
            if value is not None and value.startswith("0000-"):
                raise ValueError("month year must be at least 0001")
        if self.start_month and self.end_month and self.end_month < self.start_month:
            raise ValueError("end_month precedes start_month")
        if self.is_current and self.end_month is not None:
            raise ValueError("current experience cannot have end_month")
        return self


class PreviousProjectRow(_RowModel):
    name: _NonBlank
    description: _NonBlank


class ProfessionalCollectionsRow(_RowModel):
    skills: list[SkillRow]
    experience: list[ExperienceRow]
    previous_projects: list[PreviousProjectRow]


class _IndustryRow(_RowModel):
    name: _NonBlank


class _CompanySizeRow(_RowModel):
    band: Literal["0-10", "11-100", "101-1000", "1001+"]


class _CountryGeographyRow(_RowModel):
    kind: Literal["country"]
    value: _NonBlank


class _RegionGeographyRow(_RowModel):
    kind: Literal["region"]
    value: _NonBlank


_GeographyRow = Annotated[
    _CountryGeographyRow | _RegionGeographyRow, Field(discriminator="kind")
]


class _CompanyExclusionRow(_RowModel):
    kind: Literal["company"]
    company_id: UUID


class _IndustryExclusionRow(_RowModel):
    kind: Literal["industry"]
    name: _NonBlank


class _GeographyExclusionRow(_RowModel):
    kind: Literal["geography"]
    geography: _GeographyRow


_ExclusionRow = Annotated[
    _CompanyExclusionRow | _IndustryExclusionRow | _GeographyExclusionRow,
    Field(discriminator="kind"),
]


class IdealClientProfileRow(_RowModel):
    id: UUID
    user_id: UUID
    name: _NonBlank
    industries: list[_IndustryRow]
    company_sizes: list[_CompanySizeRow]
    geographies: list[_GeographyRow]
    exclusions: list[_ExclusionRow]
    created_at: datetime
    updated_at: datetime


class ClientDiscoveryStrategyRow(_RowModel):
    id: UUID
    user_id: UUID
    name: _NonBlank
    service_offering_id: UUID
    ideal_client_profile_id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime
