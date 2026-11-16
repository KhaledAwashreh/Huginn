"""Business profile request models."""

from pydantic import model_validator

from huginn.management.presentation.api.primitives import NonBlankText
from huginn.management.presentation.api.requests.common import PatchRequest
from huginn.management.presentation.api.requests.professional_profile import Skill


class BusinessProfileUpdateRequest(PatchRequest):
    name: NonBlankText | None = None
    tagline: NonBlankText | None = None
    website: NonBlankText | None = None
    location: NonBlankText | None = None
    description: NonBlankText | None = None
    capabilities: list[Skill] | None = None

    @model_validator(mode="after")
    def reject_empty_patch(self):
        if not self.model_fields_set:
            raise ValueError("at least one field must be supplied")
        return self
