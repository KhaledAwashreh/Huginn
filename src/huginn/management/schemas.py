"""Professional collection boundaries; see ADR-0011."""

from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
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
