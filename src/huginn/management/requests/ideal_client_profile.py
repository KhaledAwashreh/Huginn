"""Ideal client profile request models."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from huginn.management.primitives import NonBlankText
from huginn.management.requests.common import (
    NonBlank,
    PatchRequest,
    RequestModel,
    RequestUUID,
)


class Industry(RequestModel):
    name: NonBlank


class CompanySize(RequestModel):
    band: Literal["0-10", "11-100", "101-1000", "1001+"]


class CountryGeography(RequestModel):
    kind: Literal["country"]
    value: NonBlank


class RegionGeography(RequestModel):
    kind: Literal["region"]
    value: NonBlank


Geography = Annotated[CountryGeography | RegionGeography, Field(discriminator="kind")]


class CompanyExclusion(RequestModel):
    kind: Literal["company"]
    company_id: RequestUUID


class IndustryExclusion(RequestModel):
    kind: Literal["industry"]
    name: NonBlank


class GeographyExclusion(RequestModel):
    kind: Literal["geography"]
    geography: Geography


Exclusion = Annotated[
    CompanyExclusion | IndustryExclusion | GeographyExclusion,
    Field(discriminator="kind"),
]


class IdealClientProfileCreateRequest(RequestModel):
    name: NonBlank
    industries: list[Industry] = Field(default_factory=list)
    company_sizes: list[CompanySize] = Field(default_factory=list)
    geographies: list[Geography] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)


class IdealClientProfileUpdateRequest(PatchRequest):
    name: NonBlankText | None = None
    industries: list[Industry] | None = None
    company_sizes: list[CompanySize] | None = None
    geographies: list[Geography] | None = None
    exclusions: list[Exclusion] | None = None

    @model_validator(mode="after")
    def supplied_values_cannot_be_null(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
