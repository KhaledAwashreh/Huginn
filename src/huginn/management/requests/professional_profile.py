"""Professional profile request models."""

from typing import Annotated, Self

from pydantic import Field, StringConstraints, model_validator

from huginn.management.primitives import NonBlankText
from huginn.management.requests.common import NonBlank, PatchRequest, RequestModel

Month = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]


class Skill(RequestModel):
    name: NonBlank


class Experience(RequestModel):
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


class PreviousProject(RequestModel):
    name: NonBlank
    description: NonBlank


class ProfessionalCollectionsRequest(RequestModel):
    skills: list[Skill] = Field(default_factory=list)
    experience: list[Experience] = Field(default_factory=list)
    previous_projects: list[PreviousProject] = Field(default_factory=list)


class ProfessionalProfileUpdateRequest(PatchRequest):
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
