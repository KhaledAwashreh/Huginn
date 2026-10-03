"""Ideal client profile response models."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints

from huginn.management.responses.common import ResponseModel

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class IndustryResponse(ResponseModel):
    name: NonBlank


class CompanySizeResponse(ResponseModel):
    band: Literal["0-10", "11-100", "101-1000", "1001+"]


class GeographyResponse(ResponseModel):
    kind: Literal["country", "region"]
    value: NonBlank


class CompanyExclusionResponse(ResponseModel):
    kind: Literal["company"]
    company_id: UUID


class IndustryExclusionResponse(ResponseModel):
    kind: Literal["industry"]
    name: NonBlank


class GeographyExclusionResponse(ResponseModel):
    kind: Literal["geography"]
    geography: GeographyResponse


ExclusionResponse = Annotated[
    CompanyExclusionResponse | IndustryExclusionResponse | GeographyExclusionResponse,
    Field(discriminator="kind"),
]


class IdealClientProfileResponse(ResponseModel):
    id: UUID
    user_id: UUID
    name: NonBlank
    industries: list[IndustryResponse]
    company_sizes: list[CompanySizeResponse]
    geographies: list[GeographyResponse]
    exclusions: list[ExclusionResponse]
    created_at: datetime
    updated_at: datetime
