"""Professional profile response models."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import StringConstraints, model_validator

from huginn.management.responses.common import ResponseModel

NonBlank = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Month = Annotated[str, StringConstraints(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]


class SkillResponse(ResponseModel):
    name: NonBlank


class ExperienceResponse(ResponseModel):
    organization: NonBlank
    role: NonBlank
    summary: NonBlank | None
    start_month: Month | None
    end_month: Month | None
    is_current: bool

    @model_validator(mode="after")
    def months_are_valid(self):
        for value in (self.start_month, self.end_month):
            if value is not None and value.startswith("0000-"):
                raise ValueError("month year must be at least 0001")
        if self.start_month and self.end_month and self.end_month < self.start_month:
            raise ValueError("end_month precedes start_month")
        if self.is_current and self.end_month is not None:
            raise ValueError("current experience cannot have end_month")
        return self


class PreviousProjectResponse(ResponseModel):
    name: NonBlank
    description: NonBlank


class ProfessionalProfileResponse(ResponseModel):
    id: UUID
    user_id: UUID
    headline: NonBlank | None
    professional_summary: NonBlank | None
    skills: list[SkillResponse]
    experience: list[ExperienceResponse]
    previous_projects: list[PreviousProjectResponse]
    created_at: datetime
    updated_at: datetime
