"""Professional collection boundaries; see ADR-0011."""

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

from huginn.management.primitives import (
    E164Phone,
    Email,
    IanaTimezone,
    NonBlankText,
    PatchModel,
    UUIDValue,
)

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Month = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$"),
]


class BoundaryModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class Skill(BoundaryModel):
    name: NonBlank


class Experience(BoundaryModel):
    organization: NonBlank
    role: NonBlank
    summary: NonBlank | None = None
    start_month: Month | None = None
    end_month: Month | None = None
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


class PreviousProject(BoundaryModel):
    name: NonBlank
    description: NonBlank


class ProfessionalCollections(BoundaryModel):
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    previous_projects: list[PreviousProject] = Field(default_factory=list)


class UserRead(BoundaryModel):
    id: UUIDValue
    first_name: NonBlank
    last_name: NonBlank
    email: Email
    phone_number: E164Phone
    country_of_residence: NonBlank
    timezone: IanaTimezone | None
    created_at: datetime
    updated_at: datetime


class UserPatch(PatchModel):
    first_name: NonBlankText | None = None
    last_name: NonBlankText | None = None
    email: Email | None = None
    phone_number: E164Phone | None = None
    country_of_residence: NonBlankText | None = None
    timezone: IanaTimezone | None = None

    @model_validator(mode="after")
    def required_user_values_cannot_be_cleared(self) -> Self:
        for field in self.model_fields_set - {"timezone"}:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class ProfessionalProfileRead(BoundaryModel):
    id: UUIDValue
    user_id: UUIDValue
    headline: NonBlank | None
    professional_summary: NonBlank | None
    skills: list[Skill]
    experience: list[Experience]
    previous_projects: list[PreviousProject]
    created_at: datetime
    updated_at: datetime


class ProfessionalProfilePatch(PatchModel):
    headline: NonBlankText | None = None
    professional_summary: NonBlankText | None = None
    skills: list[Skill] | None = None
    experience: list[Experience] | None = None
    previous_projects: list[PreviousProject] | None = None

    @model_validator(mode="after")
    def collections_cannot_be_null(self) -> Self:
        for field in {
            "skills",
            "experience",
            "previous_projects",
        } & self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} must be an array; use [] to clear it")
        return self


class OfferingCreate(BoundaryModel):
    name: NonBlank
    description: NonBlank


class OfferingPatch(PatchModel):
    name: NonBlankText | None = None
    description: NonBlankText | None = None

    @model_validator(mode="after")
    def required_values_cannot_be_cleared(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class OfferingRead(BoundaryModel):
    id: UUIDValue
    user_id: UUIDValue
    name: NonBlank
    description: NonBlank
    created_at: datetime
    updated_at: datetime


class Industry(BoundaryModel):
    name: NonBlank


class CompanySize(BoundaryModel):
    band: Literal["0-10", "11-100", "101-1000", "1001+"]


class CountryGeography(BoundaryModel):
    kind: Literal["country"]
    value: NonBlank


class RegionGeography(BoundaryModel):
    kind: Literal["region"]
    value: NonBlank


Geography = Annotated[CountryGeography | RegionGeography, Field(discriminator="kind")]


class CompanyExclusion(BoundaryModel):
    kind: Literal["company"]
    company_id: Annotated[UUID, Field(strict=True)]


class IndustryExclusion(BoundaryModel):
    kind: Literal["industry"]
    name: NonBlank


class GeographyExclusion(BoundaryModel):
    kind: Literal["geography"]
    geography: Geography


Exclusion = Annotated[
    CompanyExclusion | IndustryExclusion | GeographyExclusion,
    Field(discriminator="kind"),
]


class IcpCreate(BoundaryModel):
    name: NonBlank
    industries: list[Industry] = Field(default_factory=list)
    company_sizes: list[CompanySize] = Field(default_factory=list)
    geographies: list[Geography] = Field(default_factory=list)
    exclusions: list[Exclusion] = Field(default_factory=list)


class IcpPatch(PatchModel):
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


class IcpRead(BoundaryModel):
    id: UUIDValue
    user_id: UUIDValue
    name: NonBlank
    industries: list[Industry]
    company_sizes: list[CompanySize]
    geographies: list[Geography]
    exclusions: list[Exclusion]
    created_at: datetime
    updated_at: datetime


class StrategyCreate(BoundaryModel):
    name: NonBlank
    service_offering_id: UUIDValue
    ideal_client_profile_id: UUIDValue
    is_active: bool = False


class StrategyPatch(PatchModel):
    name: NonBlankText | None = None
    service_offering_id: UUIDValue | None = None
    ideal_client_profile_id: UUIDValue | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def supplied_values_cannot_be_null(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class StrategyRead(BoundaryModel):
    id: UUIDValue
    user_id: UUIDValue
    name: NonBlank
    service_offering_id: UUIDValue
    ideal_client_profile_id: UUIDValue
    is_active: bool
    created_at: datetime
    updated_at: datetime
