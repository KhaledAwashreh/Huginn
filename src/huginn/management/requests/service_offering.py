"""Service offering request models."""

from typing import Self

from pydantic import model_validator

from huginn.management.primitives import NonBlankText
from huginn.management.requests.common import NonBlank, PatchRequest, RequestModel


class ServiceOfferingCreateRequest(RequestModel):
    name: NonBlank
    description: NonBlank


class ServiceOfferingUpdateRequest(PatchRequest):
    name: NonBlankText | None = None
    description: NonBlankText | None = None

    @model_validator(mode="after")
    def required_values_cannot_be_null(self) -> Self:
        for field in self.model_fields_set:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self
